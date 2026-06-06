from __future__ import annotations

from agent.types import AgentConfig, Issue

def build_system_prompt(config: AgentConfig, issue: Issue) -> str:
    return f"""You are an expert Go developer. Your task is to fix a GitHub issue by editing source code in a Go repository.

## Repository
{config.repo} (cloned locally)

## Issue #{issue.number}: {issue.title}
{issue.body}

## Rules
- Use search_code and read_file to understand the codebase BEFORE making any edits.
- Make the MINIMAL change needed to fix the issue. Do not refactor unrelated code.
- After editing, ALWAYS call run_validation to verify your changes compile, pass vet, and pass tests.
- If validation fails, read the errors carefully, fix them, and validate again.
- Do NOT add new dependencies.
- Do NOT change code unrelated to the issue.
- If editing test files, make sure your test cases actually test the fix.

## Strategy
1. Search for relevant code related to the issue keywords, error messages, or function names.
2. Read the key files to understand the current behavior and conventions.
3. Plan your minimal fix — identify exactly what needs to change and why.
4. Apply edits with edit_file (one logical change at a time).
5. Run validation with run_validation.
6. If validation fails, analyze errors, fix, and re-validate.
7. When all checks pass, summarize what you changed and why.

When you are done (all validation passes), end your response with a summary of the changes. Do not call any more tools after validation passes."""


def build_explore_prompt(config: AgentConfig, issue: Issue) -> str:
    return f"""You are an expert Go developer investigating a GitHub issue.

## Repository
{config.repo} (cloned locally)

## Issue #{issue.number}: {issue.title}
{issue.body}

## Your Task
Use the read-only tools to understand the codebase and identify the root cause. Do NOT edit any files.

## Available Tools
- search_code: search for patterns in the codebase
- read_file: read file contents with line numbers
- list_dir: list directory contents
- find_symbol: find Go symbol definitions and usages

## Strategy
1. Search for keywords from the issue (error messages, function names, types).
2. Read the relevant files to understand current behavior.
3. Identify the root cause — what exactly is wrong and where.
4. Find the exact code that needs to change.

## When Done
When you have enough understanding, stop calling tools and produce a summary with these sections:
1. **Root Cause**: What is wrong and why
2. **Relevant Files**: File paths and line ranges involved
3. **Key Code Snippets**: Copy the exact code that needs to change
4. **Fix Direction**: Your idea for the minimal fix"""


def build_plan_prompt(issue: Issue, exploration_summary: str) -> str:
    return f"""You are an expert Go developer. Based on the exploration below, produce a precise edit plan.

IMPORTANT: You have NO tools available. Do NOT call any functions. Do NOT output tool calls.
Respond with plain text only — your edit plan.

## Issue #{issue.number}: {issue.title}
{issue.body}

## Exploration Summary
{exploration_summary}

## Instructions
Produce a concrete edit plan. For EACH edit, specify:
1. **File**: exact relative path from repo root
2. **old_str**: the EXACT string to find in the file (copy from the exploration summary or from file contents you read earlier in the conversation)
3. **new_str**: the EXACT replacement string
4. **Reason**: why this change fixes the issue

Also specify:
- Validation scope (e.g. './...' or a specific package path)
- Whether test files need changes and what test cases to add

Rules:
- Be minimal. Do not change unrelated code.
- Do NOT add new dependencies.
- Make sure old_str is unique in the file (include enough surrounding context).
- Prefer the smallest change that correctly fixes the issue.
- Do NOT call any tools. Just produce the plan as text."""


def build_apply_prompt(config: AgentConfig, issue: Issue, plan: str) -> str:
    return f"""You are an expert Go developer. Execute the edit plan below.

## Repository
{config.repo} (cloned locally)

## Issue #{issue.number}: {issue.title}

## Edit Plan
{plan}

## Available Tools
- edit_file: apply a find-and-replace edit (old_str must match exactly once)
- read_file: re-read a file to verify exact strings before editing
- run_validation: run gofmt, go build, go vet, go test

## Instructions
1. Apply each edit from the plan using edit_file.
2. If old_str doesn't match, use read_file to find the correct exact string, then retry.
3. After ALL edits are applied, call run_validation.
4. If validation fails, read the errors, fix with more edits, and validate again.
5. When validation passes, stop and summarize what you changed.

Do NOT search or explore. The exploration is done. Focus on editing and validating."""


def build_explore_summary_nudge() -> str:
    return (
        "You have used all exploration iterations. Stop exploring and produce your "
        "summary now. Include these sections:\n"
        "1. **Root Cause**: What is wrong and why\n"
        "2. **Relevant Files**: File paths and line ranges\n"
        "3. **Key Code Snippets**: Exact code that needs to change\n"
        "4. **Fix Direction**: Your minimal fix idea"
    )


def build_review_prompt(issue: Issue, diff: str) -> str:
    return f"""You are a senior Go developer reviewing a patch for a GitHub issue.

## Issue #{issue.number}: {issue.title}
{issue.body}

## Patch (git diff)
```diff
{diff}
```

## Review Instructions
Evaluate whether this patch correctly and completely fixes the issue. Consider:
1. Does the change address the root cause described in the issue?
2. Are there edge cases the patch misses?
3. Does the code follow Go conventions?
4. Are tests added or updated to cover the fix?
5. Are there any unintended side effects or unrelated changes?

## Response Format
Start your response with EXACTLY one of:
- `VERDICT: FIXED` — if the patch correctly fixes the issue
- `VERDICT: NOT FIXED` — if the patch is wrong, incomplete, or has problems

Then explain your reasoning. If NOT FIXED, describe specifically what needs to change."""


def build_pr_prompt(issue: Issue, diff: str) -> str:
    return f"""Write a pull request title and body for the following change to a Go project.

## Issue #{issue.number}: {issue.title}
{issue.body}

## Diff
```diff
{diff}
```

## Instructions
- Title: imperative mood, under 72 characters, describes the fix (e.g. "Fix UUID validation to accept uppercase hex digits")
- Body: explain what was wrong, what this change does, and how it fixes the issue. Use markdown.
- Be concise and factual. Do not add unnecessary commentary.

Respond with EXACTLY this format:
TITLE: <title>
BODY:
<body>"""


def build_compare_prompt(issue: Issue, accepted_diff: str, agent_diff: str) -> str:
    return f"""Compare these two approaches to fixing the same GitHub issue.

## Issue #{issue.number}: {issue.title}
{issue.body}

## Accepted PR Diff (ground truth — this was merged by the maintainers)
```diff
{accepted_diff}
```

## Agent-Generated Diff
```diff
{agent_diff}
```

## Analysis Required
Compare the two diffs on these axes:

1. **Files touched**: Same files or different?
2. **Root cause**: Did both identify the same underlying problem?
3. **Fix approach**: Exact match / functionally equivalent / different approach / wrong fix?
4. **Code quality**: Which is more idiomatic Go?
5. **Scope**: Which is more minimal? Any unnecessary changes?
6. **Tests**: How do the test changes compare?

Write your analysis as markdown. Be honest about where the agent's output diverges from the accepted fix."""
