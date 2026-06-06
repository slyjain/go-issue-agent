# Go Issue Agent

An agentic AI platform that works on issues from open-source Go projects and generates production-quality fixes.

## How It Works

```
GitHub Issue → Fetch & Clone Repo → AI Agent Loop → Patch + PR Description
```

1. **Fetches** the issue details and clones the target Go repository
2. **AI agent loop** iterates using Claude to understand the codebase via tools (search, read, list, find symbol)
3. **Edits** source files with precise find-and-replace operations
4. **Validates** every edit through `gofmt → go build → go vet → go test → golangci-lint`
5. **Outputs** a patch diff and PR description

## Architecture

```
agent/
├── types.py      # Data structures (AgentConfig, Issue, ToolResult, RunSummary)
├── github.py     # GitHub API client (fetch issues, PR diffs, metadata)
├── repo.py       # Git operations (clone, checkout, branch, diff, commit)
└── tools.py      # Agent toolset (search_code, read_file, list_dir, find_symbol, edit_file, run_validation)
```

## Agent Tools

| Tool | Purpose |
|------|---------|
| `search_code` | Ripgrep-powered code search with optional glob filters |
| `read_file` | Read files with line numbers and optional line range |
| `list_dir` | List directory contents to understand project structure |
| `find_symbol` | Find Go symbol definitions and usages (func, type, var, const) |
| `edit_file` | Precise find-and-replace edits (must match exactly once) |
| `run_validation` | Full Go validation pipeline (gofmt, build, vet, test, lint) |

## Prerequisites

- Python 3.10+
- Go toolchain (`go`, `gofmt`)
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`)
- `ANTHROPIC_API_KEY` environment variable

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install anthropic

cp .env.example .env   # add your ANTHROPIC_API_KEY
```

## Usage

```bash
# Activate the virtual environment
source .venv/bin/activate

# Fetch an issue
python3 -c "
from agent.github import fetch_issue
issue = fetch_issue('go-playground/validator', 1550)
print(issue.title)
"
```

## Configuration

Configured via `AgentConfig` in `agent/types.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model` | `claude-sonnet-4-5-20250929` | Claude model to use |
| `max_iterations` | `6` | Max agent loop iterations |
| `max_tokens_total` | `200,000` | Token budget for the run |
| `temperature` | `0.0` | LLM randomness (deterministic) |
