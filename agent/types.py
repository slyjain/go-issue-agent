# Makes type hints lazy strings so that str | None syntax works on older Python versions
from __future__ import annotations

# dataclass autogenerates __init__/ __repr__ for classes
# field customises default
from dataclasses import dataclass, field
# Object-oriented file paths (Path("runs") / "output" instead of os.path.join("runs","output"))
from pathlib import Path
# Immutable tuple with named fields, like a lightweight frozen dataclass that supports _replace()
from typing import NamedTuple


@dataclass(frozen=True)
class AgentConfig:
    repo: str
    issue_number: int
    base_commit: str | None = None
    max_iterations: int = 6
    max_tokens_total: int = 200_000
    # OpenRouter model — one model for all phases
    model: str = "deepseek/deepseek-v4-pro"
    # LLM randomness is 0
    temperature: float = 0.0
    workdir: Path = Path("workspace")
    output_dir: Path = Path("runs")


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    labels: list[str]
    url: str


class ToolResult(NamedTuple):
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class RunSummary:
    issue: Issue
    iterations: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tools_called: int = 0
    validation_passed: bool = False
    files_changed: list[str] = field(default_factory=list)
    error: str | None = None
    phases_completed: list[str] = field(default_factory=list)
