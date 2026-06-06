from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from agent.types import AgentConfig

def build_config(args)-> AgentConfig:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    repo = args.repo
    issue = args.issue
    output_dir = Path("runs") / f"{repo.replace('/', '_')}_issue{issue}_{now}"

    return AgentConfig(
        repo=repo,
        issue_number=issue,
        base_commit=getattr(args, "base_commit", None),
        max_iterations=int(
            getattr(args, "max_iterations", None) or 0
        ) or int(os.environ.get("AGENT_MAX_ITERATIONS", "6")),
        max_tokens_total=int(os.environ.get("AGENT_MAX_TOKENS", "200000")),
        model=getattr(args, "model", None)
        or os.environ.get("AGENT_MODEL", "deepseek/deepseek-v4-pro"),
        temperature=0.0,
        workdir=Path("workspace") / repo.replace("/", "_"),
        output_dir=output_dir,
    )