"""Tests for agent/github.py — GitHub API client (requires network)."""
import pytest

from agent.github import fetch_issue, fetch_pr_diff, fetch_pr_metadata


@pytest.mark.network
class TestFetchIssue:
    def test_fetch_known_issue(self):
        issue = fetch_issue("go-playground/validator", 1550)
        assert issue.number == 1550
        assert "UUID" in issue.title
        assert isinstance(issue.body, str)
        assert isinstance(issue.labels, list)
        assert "github.com" in issue.url

    def test_fetch_issue_with_labels(self):
        issue = fetch_issue("go-playground/validator", 1481)
        assert issue.number == 1481
        assert len(issue.labels) > 0


@pytest.mark.network
class TestFetchPrDiff:
    def test_fetch_known_pr(self):
        diff = fetch_pr_diff("go-playground/validator", 1551)
        assert isinstance(diff, str)
        assert len(diff) > 0
        assert "diff" in diff.lower() or "---" in diff or "+++" in diff


@pytest.mark.network
class TestFetchPrMetadata:
    def test_fetch_known_pr(self):
        meta = fetch_pr_metadata("go-playground/validator", 1551)
        assert "title" in meta
        assert "body" in meta
        assert "base_sha" in meta
        assert "head_sha" in meta
        assert "merged" in meta
