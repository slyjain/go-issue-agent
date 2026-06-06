"""Tests for agent/localizer.py — deterministic repo localization."""
from pathlib import Path

import pytest

from agent.localizer import (
    localize,
    _extract_keywords,
    _build_repo_tree,
    _build_file_skeletons,
    _keyword_localize,
    _find_related_tests,
    _read_top_functions,
)
from agent.types import Issue


@pytest.fixture
def sample_issue():
    return Issue(
        number=1550,
        title="[Bug]: UUID validation fails for uppercase UUIDs",
        body="When validating UUIDs with the uuid tag, uppercase hex digits are rejected.",
        labels=["bug"],
        url="https://github.com/go-playground/validator/issues/1550",
    )


@pytest.fixture
def go_repo(tmp_path):
    """Create a minimal Go repo for testing."""
    (tmp_path / "main.go").write_text(
        "package main\n\n"
        "func main() {}\n\n"
        "func isUUID(s string) bool {\n"
        "\treturn len(s) == 36\n"
        "}\n\n"
        "func isAlpha(s string) bool {\n"
        "\treturn true\n"
        "}\n"
    )
    (tmp_path / "util.go").write_text(
        "package main\n\n"
        "type Validator struct {\n"
        "\tname string\n"
        "}\n\n"
        "var defaultValidator = Validator{}\n\n"
        "const maxLen = 100\n"
    )
    (tmp_path / "main_test.go").write_text(
        "package main\n\n"
        "import \"testing\"\n\n"
        "func TestUUIDValidation(t *testing.T) {\n"
        "\t// test\n"
        "}\n\n"
        "func TestAlphaValidation(t *testing.T) {\n"
        "\t// test\n"
        "}\n"
    )
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "helper.go").write_text("package pkg\n\nfunc Helper() {}\n")
    return tmp_path


class TestExtractKeywords:
    def test_extracts_meaningful_words(self, sample_issue):
        keywords = _extract_keywords(sample_issue)
        assert "uuid" in keywords or "uuids" in keywords
        assert "uppercase" in keywords
        # Stopwords removed
        assert "the" not in keywords
        assert "for" not in keywords

    def test_removes_short_words(self):
        issue = Issue(number=1, title="a b cd efg", body="", labels=[], url="")
        keywords = _extract_keywords(issue)
        assert "a" not in keywords
        assert "b" not in keywords
        assert "cd" not in keywords
        assert "efg" in keywords

    def test_max_10_keywords(self):
        long_title = " ".join(f"keyword{i}" for i in range(20))
        issue = Issue(number=1, title=long_title, body="", labels=[], url="")
        keywords = _extract_keywords(issue)
        assert len(keywords) <= 10


class TestBuildRepoTree:
    def test_lists_go_files(self, go_repo):
        tree = _build_repo_tree(go_repo)
        assert "main.go" in tree
        assert "util.go" in tree
        assert "main_test.go" in tree
        assert "helper.go" in tree

    def test_shows_line_counts(self, go_repo):
        tree = _build_repo_tree(go_repo)
        assert "lines)" in tree

    def test_skips_hidden_dirs(self, go_repo):
        (go_repo / ".git").mkdir()
        (go_repo / ".git" / "config.go").write_text("package git\n")
        tree = _build_repo_tree(go_repo)
        assert "config.go" not in tree


class TestBuildFileSkeletons:
    def test_finds_declarations(self, go_repo):
        skeletons = _build_file_skeletons(go_repo)
        assert "func main()" in skeletons
        assert "func isUUID" in skeletons
        assert "type Validator struct" in skeletons
        assert "var defaultValidator" in skeletons
        assert "const maxLen" in skeletons

    def test_skips_test_files(self, go_repo):
        skeletons = _build_file_skeletons(go_repo)
        assert "TestUUID" not in skeletons


class TestKeywordLocalize:
    def test_ranks_files(self, go_repo):
        text, ranked = _keyword_localize(["uuid", "alpha"], go_repo)
        assert len(ranked) > 0
        assert "main.go" in ranked  # has both isUUID and isAlpha

    def test_no_matches(self, go_repo):
        text, ranked = _keyword_localize(["nonexistent_xyz"], go_repo)
        assert ranked == []


class TestFindRelatedTests:
    def test_finds_test_functions(self, go_repo):
        result = _find_related_tests(["uuid", "alpha"], go_repo)
        assert "TestUUID" in result or "TestAlpha" in result

    def test_no_matches(self, go_repo):
        result = _find_related_tests(["nonexistent_xyz"], go_repo)
        assert "no matching" in result.lower() or result.strip() == ""


class TestReadTopFunctions:
    def test_reads_matching_functions(self, go_repo):
        result = _read_top_functions(go_repo, ["main.go"], ["uuid"])
        assert "isUUID" in result
        assert "len(s) == 36" in result

    def test_no_matches(self, go_repo):
        result = _read_top_functions(go_repo, ["main.go"], ["nonexistent"])
        assert "no matching" in result.lower()


class TestLocalize:
    def test_produces_all_sections(self, go_repo, sample_issue):
        result = localize(sample_issue, go_repo)
        assert "## Repository Structure" in result
        assert "## File Skeletons" in result
        assert "## Keyword Localization" in result
        assert "## Related Tests" in result
        assert "## Key Functions" in result

    def test_returns_string(self, go_repo, sample_issue):
        result = localize(sample_issue, go_repo)
        assert isinstance(result, str)
        assert len(result) > 100
