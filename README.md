# Go Issue Agent

An agentic AI platform that works on issues from open-source Go projects and generates production-quality fixes. Uses LLMs via [OpenRouter](https://openrouter.ai/) (OpenAI-compatible API).

## How It Works

```
GitHub Issue → Fetch & Clone Repo → AI Agent Loop → Patch + PR Description
```

1. **Fetches** the issue details and clones the target Go repository
2. **AI agent loop** iterates using an LLM (via OpenRouter) to understand the codebase via tools (search, read, list, find symbol)
3. **Edits** source files with precise find-and-replace operations
4. **Validates** every edit through `gofmt → go build → go vet → go test → golangci-lint`
5. **Generates** a PR title, body, and patch diff
6. **Compares** agent output against accepted PRs for quality evaluation

## Architecture

```
agent/
├── types.py      # Data structures (AgentConfig, Issue, ToolResult, RunSummary)
├── github.py     # GitHub API client (fetch issues, PR diffs, metadata)
├── repo.py       # Git operations (clone, checkout, branch, diff, commit)
├── tools.py      # Agent toolset (search, read, edit, validate)
└── prompts.py    # System prompts (agent instructions, PR generation, diff comparison)
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

## Prompt System

The agent uses three prompt templates (`agent/prompts.py`):

| Prompt | Purpose |
|--------|---------|
| `build_system_prompt` | Instructs the AI on how to investigate and fix a Go issue |
| `build_pr_prompt` | Generates a PR title and body from the issue and diff |
| `build_compare_prompt` | Compares agent-generated fix against the accepted PR diff |

## Prerequisites

- Python 3.10+
- Go toolchain (`go`, `gofmt`)
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`)
- [OpenRouter](https://openrouter.ai/) API key

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install openai
```

Create a `.env` file:

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

## Usage

```bash
source .venv/bin/activate

# Fetch an issue
python3 -c "
from agent.github import fetch_issue
issue = fetch_issue('go-playground/validator', 1550)
print(issue.title)
"

# Clone a repo and search code
python3 -c "
from agent.tools import execute_tool
from agent.repo import clone_repo
from pathlib import Path
clone_repo('go-playground/validator', Path('workspace/test'))
r = execute_tool('search_code', {'query': 'uuid', 'glob': '*.go'}, Path('workspace/test'))
print(r.content[:300])
"
```

## Configuration

Configured via `AgentConfig` in `agent/types.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model` | `anthropic/claude-sonnet-4-5` | OpenRouter model identifier |
| `max_iterations` | `6` | Max agent loop iterations |
| `max_tokens_total` | `200,000` | Token budget for the run |
| `temperature` | `0.0` | LLM randomness (deterministic) |
| `workdir` | `workspace/` | Directory for cloned repos |
| `output_dir` | `runs/` | Directory for run outputs |

Any model available on OpenRouter can be used by changing the `model` parameter (e.g. `google/gemini-2.5-pro`, `openai/gpt-4o`, `anthropic/claude-sonnet-4-5`).
