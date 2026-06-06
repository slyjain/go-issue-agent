"""Deterministic repo localization — zero LLM calls.

Extracts repo structure, file skeletons, keyword matches, related tests,
and key function bodies to give the agent a head start before EXPLORE.
"""
from __future__ import annotations

import os
import re
import subprocess
from collections import Counter
from pathlib import Path

from agent.types import Issue

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "and", "but", "or", "nor", "not", "no", "so", "if",
    "then", "than", "too", "very", "just", "about", "above", "below",
    "between", "i", "me", "my", "we", "our", "you", "your", "he", "she",
    "it", "its", "they", "them", "their", "this", "that", "these", "when",
    "where", "how", "what", "which", "who", "whom", "bug", "issue", "fix",
    "please", "also", "using", "used", "use", "like", "example", "expected",
    "actual", "behavior", "should", "does", "work", "working", "works",
}

MAX_SKELETON_LINES = 200
MAX_FUNCTION_LINES = 50
MAX_FUNCTIONS = 3
MAX_KEYWORD_FILES = 5


def localize(issue: Issue, workdir: Path) -> str:
    """Run all localization steps, return a formatted context string."""
    keywords = _extract_keywords(issue)
    repo_tree = _build_repo_tree(workdir)
    skeletons = _build_file_skeletons(workdir)
    keyword_matches, ranked_files = _keyword_localize(keywords, workdir)
    related_tests = _find_related_tests(keywords, workdir)
    key_functions = _read_top_functions(workdir, ranked_files, keywords)

    sections = [
        f"## Repository Structure\n{repo_tree}",
        f"## File Skeletons (Go declarations)\n{skeletons}",
        f"## Keyword Localization\nKeywords extracted: {', '.join(keywords)}\n\n{keyword_matches}",
        f"## Related Tests\n{related_tests}",
        f"## Key Functions (most relevant code)\n{key_functions}",
    ]
    return "\n\n".join(sections)


def _extract_keywords(issue: Issue) -> list[str]:
    """Extract meaningful keywords from issue title + body."""
    text = f"{issue.title} {issue.body}"
    # Split on non-alphanumeric, lowercase, filter stopwords and short words
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text)
    words = [w.lower() for w in words if len(w) > 2 and w.lower() not in STOPWORDS]
    # Deduplicate preserving order, take top 10 by frequency
    counts = Counter(words)
    seen = set()
    unique = []
    for word, _ in counts.most_common(15):
        if word not in seen:
            seen.add(word)
            unique.append(word)
    return unique[:10]


def _build_repo_tree(workdir: Path) -> str:
    """Build a tree of .go files with line counts."""
    lines = []
    for root, dirs, files in os.walk(workdir):
        # Skip hidden dirs, vendor, testdata
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('vendor', 'testdata')]
        rel = Path(root).relative_to(workdir)
        go_files = sorted(f for f in files if f.endswith('.go'))
        for f in go_files:
            fpath = Path(root) / f
            try:
                line_count = sum(1 for _ in open(fpath))
            except OSError:
                line_count = 0
            display_path = str(rel / f) if str(rel) != '.' else f
            lines.append(f"  {display_path} ({line_count} lines)")
    return "\n".join(lines) if lines else "(no .go files found)"


def _build_file_skeletons(workdir: Path) -> str:
    """Extract function/type/var/const declarations from all Go files."""
    result = subprocess.run(
        ["grep", "-rn", r"^\(func \|type \|var \|const \)", "--include=*.go", "."],
        cwd=workdir, capture_output=True, text=True,
    )
    if not result.stdout.strip():
        # Fallback: try with extended regex
        result = subprocess.run(
            ["grep", "-rnE", r"^(func |type |var |const )", "--include=*.go", "."],
            cwd=workdir, capture_output=True, text=True,
        )
    lines = result.stdout.strip().split("\n")
    if not lines or lines == ['']:
        return "(no declarations found)"
    # Group by file
    by_file: dict[str, list[str]] = {}
    for line in lines:
        parts = line.split(":", 2)
        if len(parts) >= 3:
            filepath = parts[0].lstrip("./")
            lineno = parts[1]
            decl = parts[2].strip()
            # Truncate long lines
            if len(decl) > 120:
                decl = decl[:117] + "..."
            by_file.setdefault(filepath, []).append(f"  {lineno}: {decl}")

    output = []
    total = 0
    for filepath in sorted(by_file.keys()):
        # Skip test files in skeleton to save space
        if filepath.endswith("_test.go"):
            continue
        output.append(f"{filepath}:")
        for decl in by_file[filepath]:
            output.append(decl)
            total += 1
            if total >= MAX_SKELETON_LINES:
                output.append(f"  ... (truncated at {MAX_SKELETON_LINES} declarations)")
                return "\n".join(output)
    return "\n".join(output) if output else "(no declarations found)"


def _keyword_localize(keywords: list[str], workdir: Path) -> tuple[str, list[str]]:
    """Grep each keyword, rank files by total hit count."""
    file_hits: Counter[str] = Counter()
    keyword_detail: dict[str, dict[str, int]] = {}

    for kw in keywords:
        result = subprocess.run(
            ["rg", "-c", "-i", "--glob", "*.go", kw, "."],
            cwd=workdir, capture_output=True, text=True,
        )
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                filepath, count_str = line.rsplit(":", 1)
                filepath = filepath.lstrip("./")
                try:
                    count = int(count_str)
                except ValueError:
                    continue
                file_hits[filepath] += count
                keyword_detail.setdefault(filepath, {})[kw] = count

    if not file_hits:
        return "(no keyword matches found)", []

    ranked = file_hits.most_common(MAX_KEYWORD_FILES)
    lines = []
    for filepath, total in ranked:
        detail = keyword_detail.get(filepath, {})
        breakdown = ", ".join(f"{k}:{v}" for k, v in detail.items())
        lines.append(f"  {filepath}: {total} hits ({breakdown})")

    ranked_files = [f for f, _ in ranked]
    return "\n".join(lines), ranked_files


def _find_related_tests(keywords: list[str], workdir: Path) -> str:
    """Find test functions whose names match any keyword."""
    pattern = "|".join(f"[Tt]est.*{re.escape(kw)}" for kw in keywords[:5])
    if not pattern:
        return "(no keywords to search)"

    result = subprocess.run(
        ["rg", "-n", "--glob", "*_test.go", f"func ({pattern})", "."],
        cwd=workdir, capture_output=True, text=True,
    )
    if not result.stdout.strip():
        # Try case-insensitive
        result = subprocess.run(
            ["rg", "-ni", "--glob", "*_test.go", f"func .*(Test|test).*({'|'.join(keywords[:5])})", "."],
            cwd=workdir, capture_output=True, text=True,
        )

    lines = result.stdout.strip().split("\n")
    if not lines or lines == ['']:
        return "(no matching test functions found)"

    # Deduplicate and limit
    seen = set()
    output = []
    for line in lines[:20]:
        clean = line.lstrip("./")
        if clean not in seen:
            seen.add(clean)
            output.append(f"  {clean}")
    return "\n".join(output)


def _read_top_functions(workdir: Path, ranked_files: list[str], keywords: list[str]) -> str:
    """Read the bodies of functions matching keywords in the top ranked files."""
    if not ranked_files or not keywords:
        return "(no functions to read)"

    output = []
    functions_read = 0

    for filepath in ranked_files[:3]:
        fpath = workdir / filepath
        if not fpath.exists() or filepath.endswith("_test.go"):
            continue

        try:
            file_lines = fpath.read_text().split("\n")
        except OSError:
            continue

        # Find function declarations matching any keyword
        for i, line in enumerate(file_lines):
            if not line.startswith("func "):
                continue
            func_name_match = re.match(r'func\s+(?:\(.*?\)\s+)?(\w+)', line)
            if not func_name_match:
                continue
            func_name = func_name_match.group(1).lower()

            if not any(kw in func_name for kw in keywords):
                continue

            # Extract function body (up to next func or MAX_FUNCTION_LINES)
            end = min(i + MAX_FUNCTION_LINES, len(file_lines))
            for j in range(i + 1, end):
                if file_lines[j].startswith("func "):
                    end = j
                    break

            body = "\n".join(f"{i + k + 1:4d} | {file_lines[i + k]}" for k in range(end - i))
            output.append(f"### {filepath}: {func_name_match.group(0).split('{')[0].strip()}")
            output.append(f"```go\n{body}\n```")
            functions_read += 1

            if functions_read >= MAX_FUNCTIONS:
                return "\n\n".join(output)

    return "\n\n".join(output) if output else "(no matching functions found)"
