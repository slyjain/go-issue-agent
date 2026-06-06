from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from openai import OpenAI, AuthenticationError, APIError

from agent.github import fetch_issue
from agent.localizer import localize
from agent.logging_ import TraceLogger, TokenTracker, print_status
from agent.prompts import (
    build_explore_prompt,
    build_plan_prompt,
    build_apply_prompt,
    build_explore_summary_nudge,
    build_review_prompt,
    build_pr_prompt,
)
from agent.repo import (
    clone_repo, clone_repo_full, checkout_commit,
    create_branch, get_diff, get_changed_files, commit_changes,
)
from agent.tools import execute_tool, get_tools_for_phase
from agent.types import AgentConfig, Issue, RunSummary

MAX_EXPLORE_ITERATIONS = 8
MAX_APPLY_ITERATIONS = 15
MAX_RETRIES = 2


def _build_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print(
            "ERROR: OPENROUTER_API_KEY is not set.\n"
            "  export OPENROUTER_API_KEY=sk-or-...",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


# ── Shared tool loop ──────────────────────────────────────────────────

def _run_tool_loop(
    client: OpenAI,
    config: AgentConfig,
    messages: list[dict],
    tools: list[dict],
    max_iterations: int,
    summary: RunSummary,
    logger: TraceLogger,
    tracker: TokenTracker,
    phase_name: str,
    max_tokens: int = 8192,
) -> str | None:
    """Generic LLM-tool loop. Returns the last assistant text content, or None.

    Uses config.model for all phases. One model for everything.
    """
    model = config.model
    last_text = None
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        summary.iterations += 1
        logger.log_iteration(summary.iterations, -1)
        print_status(f"\n[{phase_name} {iteration}/{max_iterations}] Calling {model}...")

        try:
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": config.temperature,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools
            response = client.chat.completions.create(**kwargs)
        except AuthenticationError:
            print("\nERROR: Invalid API key. Check your OPENROUTER_API_KEY.", file=sys.stderr)
            summary.error = "Authentication failed"
            return last_text
        except APIError as e:
            logger.log_event("api_error", {"error": str(e), "phase": phase_name})
            print_status(f"  API error: {e}")
            summary.error = str(e)
            return last_text

        usage = response.usage
        if usage:
            tracker.record(usage)
            summary.tokens_in = tracker.total_in
            summary.tokens_out = tracker.total_out
            logger.log_api_call(usage.prompt_tokens, usage.completion_tokens, response.choices[0].finish_reason or "unknown")
            print_status(f"  tokens: +{usage.prompt_tokens}in +{usage.completion_tokens}out (total: {tracker.total})")

        if tracker.exceeded():
            logger.log_event("budget_warning", {**tracker.summary(), "phase": phase_name})
            print_status(f"  ⚠ Over token budget ({tracker.total} > {config.max_tokens_total}) — continuing anyway")

        choice = response.choices[0]
        message = choice.message

        if message.content:
            last_text = message.content

        assistant_msg: dict = {"role": "assistant"}
        if message.content:
            assistant_msg["content"] = message.content
        if message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        messages.append(assistant_msg)

        if choice.finish_reason != "tool_calls":
            print_status(f"  Finished (finish_reason={choice.finish_reason})")
            break

        for tc in message.tool_calls:
            summary.tools_called += 1
            tool_input = json.loads(tc.function.arguments)
            print_status(f"  -> {tc.function.name}({_short_args(tool_input)})")

            result = execute_tool(tc.function.name, tool_input, config.workdir)
            result = result._replace(tool_use_id=tc.id)

            logger.log_tool_call(tc.function.name, tool_input, len(result.content), result.is_error)

            if result.is_error:
                print_status(f"     ERROR: {result.content[:100]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result.content,
            })

    return last_text


# ── Main entry point ──────────────────────────────────────────────────

def run_agent(config: AgentConfig) -> RunSummary:
    client = _build_client()

    # Fetch issue
    print_status(f"Fetching issue #{config.issue_number} from {config.repo}...")
    issue = fetch_issue(config.repo, config.issue_number)
    print_status(f"Issue: {issue.title}")

    # Clone and checkout
    if config.base_commit:
        print_status(f"Cloning {config.repo} (full, for checkout)...")
        clone_repo_full(config.repo, config.workdir)
        print_status(f"Checking out base commit {config.base_commit[:12]}...")
        checkout_commit(config.workdir, config.base_commit)
    else:
        print_status(f"Cloning {config.repo} (shallow)...")
        clone_repo(config.repo, config.workdir)

    branch_name = f"agent/fix-issue-{issue.number}"
    create_branch(config.workdir, branch_name)

    # Setup logging
    config.output_dir.mkdir(parents=True, exist_ok=True)
    logger = TraceLogger(config.output_dir / "trace.jsonl")
    tracker = TokenTracker(config.max_tokens_total)

    logger.log_event("run_start", {
        "repo": config.repo,
        "issue": issue.number,
        "model": config.model,
    })

    summary = RunSummary(issue=issue)

    # ── Phase 0: LOCALIZE (deterministic, 0 LLM calls) ──
    logger.log_event("phase_start", {"phase": "LOCALIZE"})
    print_status("\n=== PHASE 0: LOCALIZE (deterministic) ===")

    localization_context = localize(issue, config.workdir)
    print_status(f"  Localization: {len(localization_context)} chars")

    summary.phases_completed.append("LOCALIZE")
    logger.log_event("phase_end", {"phase": "LOCALIZE", "context_chars": len(localization_context)})

    # One shared conversation across all phases.
    messages: list[dict] = [
        {"role": "system", "content": build_explore_prompt(config, issue)},
        {
            "role": "user",
            "content": (
                f"Investigate issue #{issue.number}: {issue.title}\n\n{issue.body}\n\n"
                f"## Pre-computed Repository Analysis\n\n{localization_context}"
            ),
        },
    ]

    # ── Phase 1: EXPLORE ──
    logger.log_event("phase_start", {"phase": "EXPLORE"})
    print_status("\n=== PHASE 1: EXPLORE ===")

    explore_tools = get_tools_for_phase("EXPLORE")
    explore_text = _run_tool_loop(
        client, config, messages, explore_tools,
        MAX_EXPLORE_ITERATIONS, summary, logger, tracker, "EXPLORE",
    )

    if not explore_text and not summary.error:
        print_status("  Forcing exploration summary...")
        messages.append({"role": "user", "content": build_explore_summary_nudge()})
        explore_text = _run_tool_loop(
            client, config, messages, [],
            1, summary, logger, tracker, "EXPLORE-SUMMARY",
        )

    summary.phases_completed.append("EXPLORE")
    logger.log_event("phase_end", {"phase": "EXPLORE"})

    if summary.error:
        _write_outputs(config, issue, "", "", logger, tracker, summary)
        return summary

    # ── Retry loop: PLAN → APPLY → REVIEW ──
    apply_tools = get_tools_for_phase("APPLY")

    for attempt in range(MAX_RETRIES + 1):
        attempt_label = f" (attempt {attempt + 1}/{MAX_RETRIES + 1})" if attempt > 0 else ""

        # ── Phase 2: PLAN ──
        logger.log_event("phase_start", {"phase": "PLAN", "attempt": attempt})
        print_status(f"\n=== PHASE 2: PLAN{attempt_label} ===")

        plan_instruction = build_plan_prompt(issue, explore_text or "No exploration summary available.")
        messages.append({
            "role": "user",
            "content": f"=== PHASE 2: PLAN{attempt_label} ===\n\n{plan_instruction}",
        })

        plan_text = _run_tool_loop(
            client, config, messages, [],
            1, summary, logger, tracker, "PLAN",
            max_tokens=16384,
        )

        summary.phases_completed.append("PLAN")
        logger.log_event("phase_end", {"phase": "PLAN", "attempt": attempt})

        if summary.error:
            break

        # ── Phase 3: APPLY ──
        logger.log_event("phase_start", {"phase": "APPLY", "attempt": attempt})
        print_status(f"\n=== PHASE 3: APPLY{attempt_label} ===")

        apply_instruction = build_apply_prompt(config, issue, plan_text or "No plan available.")
        messages.append({
            "role": "user",
            "content": f"=== PHASE 3: APPLY{attempt_label} ===\n\n{apply_instruction}",
        })

        _run_tool_loop(
            client, config, messages, apply_tools,
            MAX_APPLY_ITERATIONS, summary, logger, tracker, "APPLY",
        )

        summary.phases_completed.append("APPLY")
        logger.log_event("phase_end", {"phase": "APPLY", "attempt": attempt})

        if summary.error:
            break

        # ── Phase 4: REVIEW ──
        diff = get_diff(config.workdir)

        if not diff.strip():
            print_status("\n  No changes produced yet.")
            if attempt < MAX_RETRIES:
                messages.append({
                    "role": "user",
                    "content": "No changes were made. Revise your plan — make sure old_str matches exactly. Try again.",
                })
                continue
            break

        logger.log_event("phase_start", {"phase": "REVIEW", "attempt": attempt})
        print_status(f"\n=== PHASE 4: REVIEW{attempt_label} ===")

        review_instruction = build_review_prompt(issue, diff)
        messages.append({
            "role": "user",
            "content": f"=== PHASE 4: REVIEW{attempt_label} ===\n\n{review_instruction}",
        })

        review_text = _run_tool_loop(
            client, config, messages, [],
            1, summary, logger, tracker, "REVIEW",
        )

        summary.phases_completed.append("REVIEW")
        logger.log_event("phase_end", {"phase": "REVIEW", "attempt": attempt})

        review_text = review_text or ""
        print_status(f"  Review verdict: {'FIXED' if 'VERDICT: FIXED' in review_text else 'NOT FIXED'}")

        if "VERDICT: FIXED" in review_text:
            print_status("  Patch approved by review!")
            break

        if attempt < MAX_RETRIES:
            print_status(f"  Retrying... ({MAX_RETRIES - attempt} retries left)")
            messages.append({
                "role": "user",
                "content": (
                    "The review found problems with your patch. "
                    "Read the review feedback above carefully. "
                    "Revise your plan and try again with a better fix."
                ),
            })
        else:
            print_status("  Max retries reached. Proceeding with current patch.")

    # ── Generate outputs ──
    diff = get_diff(config.workdir)
    changed_files = get_changed_files(config.workdir)
    summary.files_changed = changed_files

    if diff.strip():
        summary.validation_passed = "VERDICT: FIXED" in (review_text or "")

        commit_changes(config.workdir, f"fix: {issue.title} (#{issue.number})")

        print_status("\nGenerating PR description...")
        pr_text = _generate_pr(client, config, issue, diff, tracker, logger)

        _write_outputs(config, issue, diff, pr_text, logger, tracker, summary)
        print_status(f"\nDone. Output: {config.output_dir}/")
    else:
        summary.error = summary.error or "No changes produced"
        print_status("\nNo changes were made to the codebase.")
        _write_outputs(config, issue, "", "", logger, tracker, summary)

    logger.log_event("run_end", {
        "phases": summary.phases_completed,
        "iterations": summary.iterations,
        "tokens": tracker.summary(),
        "validation_passed": summary.validation_passed,
        "files_changed": summary.files_changed,
    })

    return summary


# ── Helpers ───────────────────────────────────────────────────────────

def _generate_pr(
    client: OpenAI,
    config: AgentConfig,
    issue: Issue,
    diff: str,
    tracker: TokenTracker,
    logger: TraceLogger,
) -> str:
    prompt = build_pr_prompt(issue, diff)
    try:
        response = client.chat.completions.create(
            model=config.model,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        if usage:
            tracker.record(usage)
            logger.log_api_call(usage.prompt_tokens, usage.completion_tokens, response.choices[0].finish_reason or "unknown")
        return response.choices[0].message.content or ""
    except APIError as e:
        logger.log_event("pr_gen_error", {"error": str(e)})
        return f"TITLE: Fix issue #{issue.number}\nBODY:\nFailed to generate PR description: {e}"


def _write_outputs(
    config: AgentConfig,
    issue: Issue,
    diff: str,
    pr_text: str,
    logger: TraceLogger,
    tracker: TokenTracker,
    summary: RunSummary,
) -> None:
    out = config.output_dir
    out.mkdir(parents=True, exist_ok=True)

    if diff:
        (out / "patch.diff").write_text(diff)
    if pr_text:
        (out / "PR.md").write_text(_format_pr_md(pr_text))

    (out / "summary.md").write_text(_build_summary_md(summary, tracker))


def _format_pr_md(pr_text: str) -> str:
    lines = pr_text.strip().split("\n")
    title = ""
    body_lines = []
    in_body = False

    for line in lines:
        if line.startswith("TITLE:"):
            title = line[len("TITLE:"):].strip()
        elif line.startswith("BODY:"):
            in_body = True
        elif in_body:
            body_lines.append(line)

    if not title:
        title = lines[0] if lines else "Fix"

    return f"# {title}\n\n{chr(10).join(body_lines)}\n"


def _build_summary_md(summary: RunSummary, tracker: TokenTracker) -> str:
    status = "PASSED" if summary.validation_passed else "FAILED"
    if summary.error:
        status = f"ERROR: {summary.error}"

    files = "\n".join(f"- {f}" for f in summary.files_changed) or "- (none)"
    phases = ", ".join(summary.phases_completed) or "(none)"

    return f"""# Run Summary

- **Repo**: {summary.issue.url.split('/issues/')[0].split('github.com/')[-1] if '/issues/' in summary.issue.url else 'unknown'}
- **Issue**: #{summary.issue.number} — {summary.issue.title}
- **Phases**: {phases}
- **Iterations**: {summary.iterations}
- **API calls**: {tracker.calls}
- **Tokens**: {tracker.total:,} (in: {tracker.total_in:,}, out: {tracker.total_out:,})
- **Tool calls**: {summary.tools_called}
- **Validation**: {status}

## Files Changed
{files}
"""


def _short_args(d: dict) -> str:
    parts = []
    for k, v in d.items():
        s = str(v)
        if len(s) > 40:
            s = s[:37] + "..."
        parts.append(f"{k}={s!r}")
    return ", ".join(parts)
