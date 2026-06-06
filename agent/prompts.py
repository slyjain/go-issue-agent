from __future__ import annotations

from agent.types import AgentConfig, Issue

def build_system_prompt(config: AgentConfig, issue: Issue) -> str:
    return f"""You are an expert Go developer. Your task is to fix a GitHub issue by editing source code in a Go repository.

## Repository
{config.repo} (cloned locally)

## Issue #{issue.number}: {issue.title}
{issue.body}

## Rules
- Use search_code and read_file to understand the codebase BEFORE making any edits.
- Make the MINIMAL change needed to fix the issue. Do not refactor unrelated code.
- After editing, ALWAYS call run_validation to verify your changes compile, pass vet, and pass tests.
- If validation fails, read the errors carefully, fix them, and validate again.
- Do NOT add new dependencies.
- Do NOT change code unrelated to the issue.
- If editing test files, make sure your test cases actually test the fix.

## Strategy
1. Search for relevant code related to the issue keywords, error messages, or function names.
2. Read the key files to understand the current behavior and conventions.
3. Plan your minimal fix — identify exactly what needs to change and why.
4. Apply edits with edit_file (one logical change at a time).
5. Run validation with run_validation.
6. If validation fails, analyze errors, fix, and re-validate.
7. When all checks pass, summarize what you changed and why.

When you are done (all validation passes), end your response with a summary of the changes. Do not call any more tools after validation passes."""


def build_pr_prompt(issue: Issue, diff: str) -> str:
    return f"""Write a pull request title and body for the following change to a Go project.

## Issue #{issue.number}: {issue.title}
{issue.body}

## Diff
```diff
{diff}
```

## Instructions
- Title: imperative mood, under 72 characters, describes the fix (e.g. "Fix UUID validation to accept uppercase hex digits")
- Body: explain what was wrong, what this change does, and how it fixes the issue. Use markdown.
- Be concise and factual. Do not add unnecessary commentary.

Respond with EXACTLY this format:
TITLE: <title>
BODY:
<body>"""


def build_compare_prompt(issue: Issue, accepted_diff: str, agent_diff: str) -> str:
    return f"""Compare these two approaches to fixing the same GitHub issue.

## Issue #{issue.number}: {issue.title}
{issue.body}

## Accepted PR Diff (ground truth — this was merged by the maintainers)
```diff
{accepted_diff}
```

## Agent-Generated Diff
```diff
{agent_diff}
```

## Analysis Required
Compare the two diffs on these axes:

1. **Files touched**: Same files or different?
2. **Root cause**: Did both identify the same underlying problem?
3. **Fix approach**: Exact match / functionally equivalent / different approach / wrong fix?
4. **Code quality**: Which is more idiomatic Go?
5. **Scope**: Which is more minimal? Any unnecessary changes?
6. **Tests**: How do the test changes compare?

Write your analysis as markdown. Be honest about where the agent's output diverges from the accepted fix."""
