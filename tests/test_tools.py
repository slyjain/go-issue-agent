"""Tests for agent/tools.py — tool definitions, dispatch, and execution."""
import os
from pathlib import Path

import pytest

from agent.tools import TOOL_DEFINITIONS, execute_tool, get_tools_for_phase


class TestToolDefinitions:
    def test_all_six_tools_defined(self):
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert set(names) == {
            "search_code", "read_file", "list_dir",
            "find_symbol", "edit_file", "run_validation",
        }

    def test_openai_format(self):
        for tool in TOOL_DEFINITIONS:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]
            assert tool["function"]["parameters"]["type"] == "object"


class TestGetToolsForPhase:
    def test_explore_phase(self):
        tools = get_tools_for_phase("EXPLORE")
        names = {t["function"]["name"] for t in tools}
        assert names == {"search_code", "read_file", "list_dir", "find_symbol"}

    def test_plan_phase_empty(self):
        tools = get_tools_for_phase("PLAN")
        assert tools == []

    def test_apply_phase(self):
        tools = get_tools_for_phase("APPLY")
        names = {t["function"]["name"] for t in tools}
        assert names == {"edit_file", "run_validation", "read_file"}

    def test_unknown_phase_empty(self):
        tools = get_tools_for_phase("UNKNOWN")
        assert tools == []


class TestExecuteTool:
    def test_unknown_tool_returns_error(self, tmp_path):
        result = execute_tool("nonexistent_tool", {}, tmp_path)
        assert result.is_error is True
        assert "Unknown tool" in result.content

    def test_read_file(self, tmp_path):
        (tmp_path / "hello.go").write_text("package main\n\nfunc main() {}\n")
        result = execute_tool("read_file", {"path": "hello.go"}, tmp_path)
        assert result.is_error is False
        assert "package main" in result.content
        assert "1 |" in result.content  # line numbers

    def test_read_file_not_found(self, tmp_path):
        result = execute_tool("read_file", {"path": "nope.go"}, tmp_path)
        assert result.is_error is True
        assert "not found" in result.content.lower()

    def test_read_file_with_range(self, tmp_path):
        lines = "\n".join(f"line {i}" for i in range(1, 21))
        (tmp_path / "big.go").write_text(lines)
        result = execute_tool("read_file", {"path": "big.go", "start_line": 5, "end_line": 10}, tmp_path)
        assert result.is_error is False
        assert "line 5" in result.content
        assert "line 10" in result.content
        assert "line 11" not in result.content

    def test_list_dir(self, tmp_path):
        (tmp_path / "main.go").write_text("")
        (tmp_path / "util.go").write_text("")
        (tmp_path / "pkg").mkdir()
        result = execute_tool("list_dir", {"path": "."}, tmp_path)
        assert result.is_error is False
        assert "main.go" in result.content
        assert "pkg/" in result.content

    def test_list_dir_not_found(self, tmp_path):
        result = execute_tool("list_dir", {"path": "nonexistent"}, tmp_path)
        assert result.is_error is True

    def test_edit_file_success(self, tmp_path):
        (tmp_path / "main.go").write_text("func hello() {\n\treturn\n}\n")
        result = execute_tool("edit_file", {
            "path": "main.go",
            "old_str": "func hello()",
            "new_str": "func world()",
        }, tmp_path)
        assert result.is_error is False
        assert "Successfully edited" in result.content
        assert "func world()" in (tmp_path / "main.go").read_text()

    def test_edit_file_not_found(self, tmp_path):
        result = execute_tool("edit_file", {
            "path": "nope.go",
            "old_str": "a",
            "new_str": "b",
        }, tmp_path)
        assert result.is_error is True

    def test_edit_file_no_match(self, tmp_path):
        (tmp_path / "main.go").write_text("func hello() {}\n")
        result = execute_tool("edit_file", {
            "path": "main.go",
            "old_str": "func goodbye()",
            "new_str": "func world()",
        }, tmp_path)
        assert result.is_error is True
        assert "not found" in result.content.lower()

    def test_edit_file_multiple_matches(self, tmp_path):
        (tmp_path / "main.go").write_text("return\nreturn\n")
        result = execute_tool("edit_file", {
            "path": "main.go",
            "old_str": "return",
            "new_str": "exit",
        }, tmp_path)
        assert result.is_error is True
        assert "2 times" in result.content
