"""Tests for agent/logging_.py — TraceLogger and TokenTracker."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.logging_ import TraceLogger, TokenTracker, print_status, _truncate_dict


class TestTraceLogger:
    def test_creates_file(self, tmp_path):
        log_path = tmp_path / "subdir" / "trace.jsonl"
        logger = TraceLogger(log_path)
        logger.log_event("test", {"key": "value"})
        assert log_path.exists()

    def test_writes_jsonl(self, tmp_path):
        log_path = tmp_path / "trace.jsonl"
        logger = TraceLogger(log_path)
        logger.log_event("start", {"repo": "test"})
        logger.log_event("end", {"status": "ok"})

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        event1 = json.loads(lines[0])
        assert event1["type"] == "start"
        assert event1["repo"] == "test"
        assert "ts" in event1

    def test_log_api_call(self, tmp_path):
        logger = TraceLogger(tmp_path / "trace.jsonl")
        logger.log_api_call(100, 50, "stop")
        assert logger.events[-1]["type"] == "api_call"
        assert logger.events[-1]["input_tokens"] == 100
        assert logger.events[-1]["output_tokens"] == 50

    def test_log_tool_call(self, tmp_path):
        logger = TraceLogger(tmp_path / "trace.jsonl")
        logger.log_tool_call("search_code", {"query": "uuid"}, 500, False)
        assert logger.events[-1]["type"] == "tool_call"
        assert logger.events[-1]["name"] == "search_code"

    def test_log_iteration(self, tmp_path):
        logger = TraceLogger(tmp_path / "trace.jsonl")
        logger.log_iteration(3, 10)
        assert logger.events[-1]["type"] == "iteration_start"
        assert logger.events[-1]["iteration"] == 3

    def test_events_property_returns_copy(self, tmp_path):
        logger = TraceLogger(tmp_path / "trace.jsonl")
        logger.log_event("test")
        events = logger.events
        events.clear()
        assert len(logger.events) == 1  # original unchanged


class TestTokenTracker:
    def test_initial_state(self):
        t = TokenTracker(200_000)
        assert t.total == 0
        assert t.total_in == 0
        assert t.total_out == 0
        assert t.calls == 0
        assert t.exceeded() is False

    def test_record(self):
        t = TokenTracker(200_000)
        usage = MagicMock()
        usage.prompt_tokens = 1000
        usage.completion_tokens = 500
        t.record(usage)
        assert t.total_in == 1000
        assert t.total_out == 500
        assert t.total == 1500
        assert t.calls == 1

    def test_multiple_records(self):
        t = TokenTracker(200_000)
        for _ in range(3):
            usage = MagicMock()
            usage.prompt_tokens = 100
            usage.completion_tokens = 50
            t.record(usage)
        assert t.total == 450
        assert t.calls == 3

    def test_exceeded(self):
        t = TokenTracker(100)
        usage = MagicMock()
        usage.prompt_tokens = 80
        usage.completion_tokens = 30
        t.record(usage)
        assert t.exceeded() is True

    def test_summary(self):
        t = TokenTracker(200_000)
        usage = MagicMock()
        usage.prompt_tokens = 1000
        usage.completion_tokens = 500
        t.record(usage)
        s = t.summary()
        assert s == {"total_in": 1000, "total_out": 500, "total": 1500, "api_calls": 1}


class TestTruncateDict:
    def test_short_values_unchanged(self):
        d = {"key": "short"}
        assert _truncate_dict(d) == {"key": "short"}

    def test_long_values_truncated(self):
        d = {"key": "x" * 300}
        result = _truncate_dict(d)
        assert len(result["key"]) == 203  # 200 + "..."
        assert result["key"].endswith("...")

    def test_custom_max_len(self):
        d = {"key": "x" * 50}
        result = _truncate_dict(d, max_len=10)
        assert len(result["key"]) == 13  # 10 + "..."
