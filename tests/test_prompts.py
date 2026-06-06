"""Tests for agent/prompts.py — prompt builders."""
from agent.prompts import (
    build_explore_prompt,
    build_plan_prompt,
    build_apply_prompt,
    build_review_prompt,
    build_explore_summary_nudge,
    build_pr_prompt,
    build_compare_prompt,
    build_system_prompt,
)
from agent.types import AgentConfig, Issue


def _make_issue():
    return Issue(number=1550, title="UUID bug", body="UUID fails for uppercase", labels=["bug"], url="u")


def _make_config():
    return AgentConfig(repo="go-playground/validator", issue_number=1550)


class TestExplorePrompt:
    def test_contains_issue(self):
        prompt = build_explore_prompt(_make_config(), _make_issue())
        assert "1550" in prompt
        assert "UUID" in prompt

    def test_contains_repo(self):
        prompt = build_explore_prompt(_make_config(), _make_issue())
        assert "go-playground/validator" in prompt

    def test_read_only_instructions(self):
        prompt = build_explore_prompt(_make_config(), _make_issue())
        assert "Do NOT edit" in prompt


class TestPlanPrompt:
    def test_contains_no_tools_warning(self):
        prompt = build_plan_prompt(_make_issue(), "summary here")
        assert "NO tools" in prompt
        assert "Do NOT call" in prompt

    def test_contains_exploration_summary(self):
        prompt = build_plan_prompt(_make_issue(), "found regex in regexes.go")
        assert "found regex in regexes.go" in prompt

    def test_requires_old_str_new_str(self):
        prompt = build_plan_prompt(_make_issue(), "summary")
        assert "old_str" in prompt
        assert "new_str" in prompt


class TestApplyPrompt:
    def test_contains_plan(self):
        prompt = build_apply_prompt(_make_config(), _make_issue(), "edit regexes.go line 33")
        assert "edit regexes.go line 33" in prompt

    def test_mentions_edit_file(self):
        prompt = build_apply_prompt(_make_config(), _make_issue(), "plan")
        assert "edit_file" in prompt

    def test_mentions_run_validation(self):
        prompt = build_apply_prompt(_make_config(), _make_issue(), "plan")
        assert "run_validation" in prompt


class TestReviewPrompt:
    def test_contains_verdict_format(self):
        prompt = build_review_prompt(_make_issue(), "diff content here")
        assert "VERDICT: FIXED" in prompt
        assert "VERDICT: NOT FIXED" in prompt

    def test_contains_diff(self):
        prompt = build_review_prompt(_make_issue(), "+new line\n-old line")
        assert "+new line" in prompt
        assert "-old line" in prompt


class TestExploreSummaryNudge:
    def test_mentions_root_cause(self):
        nudge = build_explore_summary_nudge()
        assert "Root Cause" in nudge

    def test_mentions_relevant_files(self):
        nudge = build_explore_summary_nudge()
        assert "Relevant Files" in nudge


class TestPrPrompt:
    def test_contains_diff(self):
        prompt = build_pr_prompt(_make_issue(), "+added\n-removed")
        assert "+added" in prompt

    def test_requires_title_format(self):
        prompt = build_pr_prompt(_make_issue(), "diff")
        assert "TITLE:" in prompt
        assert "BODY:" in prompt


class TestComparePrompt:
    def test_contains_both_diffs(self):
        prompt = build_compare_prompt(_make_issue(), "accepted diff", "agent diff")
        assert "accepted diff" in prompt
        assert "agent diff" in prompt

    def test_mentions_comparison_axes(self):
        prompt = build_compare_prompt(_make_issue(), "a", "b")
        assert "Files touched" in prompt
        assert "Root cause" in prompt


class TestSystemPrompt:
    def test_contains_issue(self):
        prompt = build_system_prompt(_make_config(), _make_issue())
        assert "1550" in prompt
        assert "UUID" in prompt
