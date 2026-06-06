from __future__ import annotations

import os
import subprocess
from pathlib import Path

from agent.tools import ToolResult

MAX_SEARCH_LINES=100
MAX_READ_LINES=500
MAX_SYMBOL_LINES=50
MAX_VALIDATION_CHARS=3000
TOOL_TIMEOUT=60

TOOL_DEFINITION=[
    {
        "name":"search_code",
        "description": (
            "Search the repository using ripgrep. Returns matching lines with "
            "file paths and line numbers. Use this FIRST to find relevant code, "
            "symbol usages, and patterns before reading files."
        ),
        "input_schema":{
            "type":"object",
            "properties":{
                "query":{
                    "type":"string",
                    "description":"Regex pattern to search for",
                },
                "glob":{
                     "type": "string",
                    "description": "Optional file glob filter, e.g. '*.go'",
                }
            },
            "required": ["query"],
        }

    },
     {
        "name": "read_file",
        "description": (
            "Read file contents with line numbers. Use after search_code to "
            "understand full context of relevant files. Optionally specify a "
            "line range to read a portion of a large file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from repo root",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read (1-indexed, optional)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to read (inclusive, optional)",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": (
            "List directory contents. Use to understand project structure "
            "and find relevant files and packages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from repo root (use '.' for root)",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "find_symbol",
        "description": (
            "Find where a Go symbol (function, type, variable, constant) is "
            "defined and used. More precise than search_code for known symbol names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The Go symbol name to find",
                },
            },
            "required": ["name"],
        },
    },
     {
        "name": "edit_file",
        "description": (
            "Apply a string replacement edit to a file. The old_str must appear "
            "EXACTLY ONCE in the file — the edit fails if there are zero or "
            "multiple matches. ALWAYS call run_validation after editing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from repo root",
                },
                "old_str": {
                    "type": "string",
                    "description": "The exact string to find and replace (must be unique in the file)",
                },
                "new_str": {
                    "type": "string",
                    "description": "The replacement string",
                },
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
     {
        "name": "run_validation",
        "description": (
            "Run the full Go validation pipeline: gofmt, go build, go vet, "
            "go test, and golangci-lint (if available). Call this AFTER EVERY "
            "edit to verify your changes compile, pass vet, and pass tests. "
            "Steps are skipped if a prerequisite fails."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": (
                        "Package scope for testing, e.g. './...' or './pkg/validate'. "
                        "Defaults to './...'."
                    ),
                },
            },
            "required": [],
        },
    },
]
#  ┌────────────────────┬─────────────────────────┬────────────────────────────┐
#   │      Feature       │          grep           │        rg (ripgrep)        │
#   ├────────────────────┼─────────────────────────┼────────────────────────────┤
#   │ Speed              │ Slow on large repos     │ 10-100x faster             │
#   ├────────────────────┼─────────────────────────┼────────────────────────────┤
#   │ .gitignore respect │ No, searches everything │ Auto-skips ignored files   │
#   ├────────────────────┼─────────────────────────┼────────────────────────────┤
#   │ node_modules, .git │ Searches inside them    │ Auto-skips them            │
#   ├────────────────────┼─────────────────────────┼────────────────────────────┤
#   │ Binary files       │ Searches them           │ Auto-skips them            │
#   ├────────────────────┼─────────────────────────┼────────────────────────────┤
#   │ Recursive search   │ Need -r flag            │ Default                    │
#   ├────────────────────┼─────────────────────────┼────────────────────────────┤
#   │ Unicode            │ Basic                   │ Full support               │
#   ├────────────────────┼─────────────────────────┼────────────────────────────┤
#   │ Output             │ Plain                   │ Colored, with line numbers │
#   └────────────────────┴─────────────────────────┴────────────────────────────┘

def execute_tool(name:str,tool_input:dict,workdir:Path)->ToolResult:
    dispatch={
        "search_code": _exec_search_code,
         "read_file": _exec_read_file,
        "list_dir": _exec_list_dir,
        "find_symbol": _exec_find_symbol,
        "edit_file": _exec_edit_file,
        "run_validation": _exec_run_validation,
    }
    fn = dispatch.get(name)
    if fn is None:
        return ToolResult(tool_use_id="", content=f"Unknown tool: {name}", is_error=True)
    try:
        content = fn(workdir, **tool_input)
        return ToolResult(tool_use_id="", content=content)
    except Exception as e:
        return ToolResult(tool_use_id="", content=f"Error: {e}", is_error=True)

def _exec_search_code(workdir:Path,query:str,glob:str|None=None,**_)->str:
    cmd = ["rg", "-n", "--no-heading", "--max-count", "5", query]
    # Glob = file path pattern matching — wildcards use karke files dhundhna.
    if glob:
        cmd += ["-g", glob]
    cmd.append(".")
    result = subprocess.run(
        cmd, cwd=workdir, capture_output=True, text=True, timeout=TOOL_TIMEOUT
    )
    lines = result.stdout.strip().split("\n")
    if not result.stdout.strip():
        return "No matches found."
    if len(lines) > MAX_SEARCH_LINES:
        lines = lines[:MAX_SEARCH_LINES]
        lines.append(f"\n... truncated to {MAX_SEARCH_LINES} lines")
    return "\n".join(lines)


def _exec_read_file(
    workdir: Path, path: str, start_line: int | None = None, end_line: int | None = None, **_
) -> str:
    
    #workdir = Path("workspace")                                                                                   
    #path = "validator.go"                                                                                             
    #fpath = workdir / path                                                  
    #Path("workspace/validator.go")   
    fpath = workdir / path
    if not fpath.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not fpath.is_file():
        raise ValueError(f"Not a file: {path}")

    with open(fpath) as f:
        all_lines = f.readlines()

    start = (start_line or 1) - 1
    end = end_line or len(all_lines)
    selected = all_lines[start:end]

    if len(selected) > MAX_READ_LINES:
        selected = selected[:MAX_READ_LINES]
        selected.append(f"... truncated to {MAX_READ_LINES} lines\n")

    numbered = [f"{start + i + 1:4d} | {line}" for i, line in enumerate(selected)]
    return "".join(numbered)

def _exec_list_dir(workdir: Path, path: str, **_) -> str:
    target = workdir / path
    if not target.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    if not target.is_dir():
        raise ValueError(f"Not a directory: {path}")

    entries = sorted(os.listdir(target))
    result = []
    for e in entries:
        full = target / e
        suffix = "/" if full.is_dir() else ""
        result.append(f"{e}{suffix}")
    return "\n".join(result)


def _exec_find_symbol(workdir: Path, name: str, **_) -> str:
    patterns = [
        f"func\\s+(\\(.*\\)\\s+)?{name}\\b",
        f"type\\s+{name}\\b",
        f"var\\s+{name}\\b",
        f"const\\s+{name}\\b",
        f'"{name}"',
    ]
    combined = "|".join(f"({p})" for p in patterns)
    cmd = ["rg", "-n", "--no-heading", "-g", "*.go", combined, "."]
    result = subprocess.run(
        cmd, cwd=workdir, capture_output=True, text=True, timeout=TOOL_TIMEOUT
    )
    lines = result.stdout.strip().split("\n")
    if not result.stdout.strip():
        return f"Symbol '{name}' not found."
    if len(lines) > MAX_SYMBOL_LINES:
        lines = lines[:MAX_SYMBOL_LINES]
        lines.append(f"\n... truncated to {MAX_SYMBOL_LINES} lines")
    return "\n".join(lines)

def _exec_edit_file(workdir: Path, path: str, old_str: str, new_str: str, **_) -> str:
    fpath = workdir / path
    if not fpath.exists():
        raise FileNotFoundError(f"File not found: {path}")

    content = fpath.read_text()
    count = content.count(old_str)

    if count == 0:
        raise ValueError(
            f"old_str not found in {path}. Make sure you're using the exact text "
            f"from the file, including whitespace and indentation."
        )
    if count > 1:
        raise ValueError(
            f"old_str appears {count} times in {path}. "
            f"Include more surrounding context to make it unique."
        )

    new_content = content.replace(old_str, new_str, 1)
    fpath.write_text(new_content)

    idx = new_content.find(new_str)
    start = max(0, new_content.rfind("\n", 0, idx) - 200)
    end = min(len(new_content), new_content.find("\n", idx + len(new_str)) + 200)
    context = new_content[start:end]

    return f"Successfully edited {path}.\n\nContext around edit:\n{context}"

def _exec_run_validation(workdir: Path, scope: str = "./...", **_) -> str:
    sections = []

    # gofmt
    fmt_result = subprocess.run(
        ["gofmt", "-l", "."],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT,
    )
    unformatted = fmt_result.stdout.strip()
    if unformatted:
        # Auto-apply formatting
        subprocess.run(
            ["gofmt", "-w", "."],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT,
        )
        sections.append(f"=== gofmt ===\n[FIXED] Formatted: {unformatted}")
    else:
        sections.append("=== gofmt ===\n[OK] No formatting issues")

    # go build
    build_result = subprocess.run(
        ["go", "build", scope],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT,
    )
    if build_result.returncode != 0:
        sections.append(f"=== go build ===\n[FAIL]\n{build_result.stderr}")
        sections.append("=== go vet ===\n[SKIP] (build failed)")
        sections.append("=== go test ===\n[SKIP] (build failed)")
        return _truncate_output("\n\n".join(sections))

    sections.append("=== go build ===\n[OK]")

    # go vet
    vet_result = subprocess.run(
        ["go", "vet", scope],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT,
    )
    if vet_result.returncode != 0:
        sections.append(f"=== go vet ===\n[FAIL]\n{vet_result.stderr}")
    else:
        sections.append("=== go vet ===\n[OK]")

    # go test
    test_result = subprocess.run(
        ["go", "test", "-count=1", "-timeout=120s", scope],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if test_result.returncode != 0:
        output = test_result.stdout + test_result.stderr
        sections.append(f"=== go test ===\n[FAIL]\n{output}")
    else:
        sections.append(f"=== go test ===\n[OK]\n{test_result.stdout[-500:]}")

    # golangci-lint (optional)
    lint_path = subprocess.run(
        ["which", "golangci-lint"], capture_output=True, text=True
    )
    if lint_path.returncode == 0:
        lint_result = subprocess.run(
            ["golangci-lint", "run", scope],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT,
        )
        if lint_result.returncode != 0:
            sections.append(f"=== golangci-lint ===\n[FAIL]\n{lint_result.stdout}{lint_result.stderr}")
        else:
            sections.append("=== golangci-lint ===\n[OK]")
    else:
        sections.append("=== golangci-lint ===\n[SKIP] (not installed)")

    return _truncate_output("\n\n".join(sections))


def _truncate_output(text: str) -> str:
    if len(text) <= MAX_VALIDATION_CHARS:
        return text
    return text[:MAX_VALIDATION_CHARS] + f"\n\n... truncated to {MAX_VALIDATION_CHARS} chars"
