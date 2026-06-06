from __future__ import annotations

from pathlib import Path

from openai import OpenAI, APIError

from agent.github import fetch_issue, fetch_pr_diff, fetch_pr_metadata
from agent.logging_ import print_status
from agent.loop import _build_client
from agent.prompts import build_compare_prompt
from agent.types import AgentConfig


def run_compare(config: AgentConfig, pr_number: int) -> None:
    client = _build_client()

    # Fetch issue and PR
    print_status(f"Fetching issue #{config.issue_number} from {config.repo}...")
    issue = fetch_issue(config.repo, config.issue_number)

    print_status(f"Fetching PR #{pr_number} diff from {config.repo}...")
    accepted_diff = fetch_pr_diff(config.repo, pr_number)

    # Find the most recent run for this issue
    agent_diff = _load_agent_diff(config)

    if not agent_diff:
        print_status("No agent diff found. Run `agent run` first.")
        return

    # Generate comparison
    print_status("Generating comparison...")
    prompt = build_compare_prompt(issue, accepted_diff, agent_diff)

    response = client.chat.completions.create(
        model=config.model,
        max_tokens=2048,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
    )

    comparison_text = response.choices[0].message.content or ""

    # Write to the run directory
    out_dir = _find_latest_run_dir(config)
    if out_dir:
        (out_dir / "comparison.md").write_text(f"# Comparison: Agent vs Accepted PR\n\n{comparison_text}\n")
        print_status(f"Written to {out_dir / 'comparison.md'}")
    else:
        # Fallback: write to config output dir
        config.output_dir.mkdir(parents=True, exist_ok=True)
        (config.output_dir / "comparison.md").write_text(f"# Comparison: Agent vs Accepted PR\n\n{comparison_text}\n")
        print_status(f"Written to {config.output_dir / 'comparison.md'}")


def _load_agent_diff(config: AgentConfig) -> str | None:
    run_dir = _find_latest_run_dir(config)
    if run_dir:
        patch = run_dir / "patch.diff"
        if patch.exists():
            return patch.read_text()
    return None


def _find_latest_run_dir(config: AgentConfig) -> Path | None:
    runs_dir = Path("runs")
    if not runs_dir.exists():
        return None

    prefix = f"{config.repo.replace('/', '_')}_issue{config.issue_number}_"
    matching = sorted(
        [d for d in runs_dir.iterdir() if d.is_dir() and d.name.startswith(prefix)],
        reverse=True,
    )
    return matching[0] if matching else None
