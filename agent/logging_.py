from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class TraceLogger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._events: list[dict] = []

    def log_event(self, event_type: str, data: dict | None = None) -> None:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **(data or {}),
        }
        self._events.append(event)
        with open(self._path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def log_api_call(self, input_tokens: int, output_tokens: int, stop_reason: str) -> None:
        self.log_event(
            "api_call",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "stop_reason": stop_reason,
            },
        )

    def log_tool_call(self, name: str, tool_input: dict, result_chars: int, is_error: bool) -> None:
        self.log_event(
            "tool_call",
            {
                "name": name,
                "input": _truncate_dict(tool_input),
                "result_chars": result_chars,
                "is_error": is_error,
            },
        )

    def log_iteration(self, n: int, max_n: int) -> None:
        self.log_event("iteration_start", {"iteration": n, "max": max_n})

    @property
    def events(self) -> list[dict]:
        return list(self._events)


class TokenTracker:
    def __init__(self, max_total: int):
        self.max_total = max_total
        self.total_in = 0
        self.total_out = 0
        self.calls = 0

    def record(self, usage) -> None:
        self.total_in += usage.prompt_tokens
        self.total_out += usage.completion_tokens
        self.calls += 1

    @property
    def total(self) -> int:
        return self.total_in + self.total_out

    def exceeded(self) -> bool:
        return self.total > self.max_total

    def summary(self) -> dict:
        return {
            "total_in": self.total_in,
            "total_out": self.total_out,
            "total": self.total,
            "api_calls": self.calls,
        }


def print_status(msg: str) -> None:
    print(f"  {msg}", file=sys.stderr)


def _truncate_dict(d: dict, max_len: int = 200) -> dict:
    out = {}
    for k, v in d.items():
        s = str(v)
        out[k] = s[:max_len] + "..." if len(s) > max_len else s
    return out
