"""Tests for agent/types.py — data structures."""
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agent.types import AgentConfig, Issue, ToolResult, RunSummary


class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig(repo="owner/repo", issue_number=42)
        assert cfg.repo == "owner/repo"
        assert cfg.issue_number == 42
        assert cfg.model == "deepseek/deepseek-v4-pro"
        assert cfg.temperature == 0.0
        assert cfg.max_iterations == 6
        assert cfg.max_tokens_total == 200_000
        assert cfg.workdir == Path("workspace")
        assert cfg.output_dir == Path("runs")
        assert cfg.base_commit is None

    def test_frozen(self):
        cfg = AgentConfig(repo="owner/repo", issue_number=1)
        with pytest.raises(FrozenInstanceError):
            cfg.repo = "other/repo"


class TestIssue:
    def test_creation(self):
        issue = Issue(
            number=1550,
            title="UUID bug",
            body="UUID validation fails",
            labels=["bug"],
            url="https://github.com/owner/repo/issues/1550",
        )
        assert issue.number == 1550
        assert issue.labels == ["bug"]

    def test_frozen(self):
        issue = Issue(number=1, title="t", body="b", labels=[], url="u")
        with pytest.raises(FrozenInstanceError):
            issue.title = "changed"


class TestToolResult:
    def test_defaults(self):
        r = ToolResult(tool_use_id="id1", content="hello")
        assert r.tool_use_id == "id1"
        assert r.content == "hello"
        assert r.is_error is False

    def test_error(self):
        r = ToolResult(tool_use_id="id2", content="fail", is_error=True)
        assert r.is_error is True

    def test_replace(self):
        r = ToolResult(tool_use_id="", content="data")
        r2 = r._replace(tool_use_id="new_id")
        assert r2.tool_use_id == "new_id"
        assert r.tool_use_id == ""  # original unchanged

    def test_unpack(self):
        r = ToolResult(tool_use_id="id", content="c", is_error=False)
        tid, content, err = r
        assert tid == "id"
        assert content == "c"
        assert err is False


class TestRunSummary:
    def test_defaults(self):
        issue = Issue(number=1, title="t", body="b", labels=[], url="u")
        s = RunSummary(issue=issue)
        assert s.iterations == 0
        assert s.tokens_in == 0
        assert s.tokens_out == 0
        assert s.tools_called == 0
        assert s.validation_passed is False
        assert s.files_changed == []
        assert s.error is None
        assert s.phases_completed == []

    def test_mutable(self):
        issue = Issue(number=1, title="t", body="b", labels=[], url="u")
        s = RunSummary(issue=issue)
        s.iterations = 5
        s.phases_completed.append("EXPLORE")
        assert s.iterations == 5
        assert s.phases_completed == ["EXPLORE"]

    def test_separate_instances_dont_share_lists(self):
        issue = Issue(number=1, title="t", body="b", labels=[], url="u")
        s1 = RunSummary(issue=issue)
        s2 = RunSummary(issue=issue)
        s1.files_changed.append("a.go")
        assert s2.files_changed == []
