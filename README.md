# Go Issue Agent

An agentic AI platform that works on issues from open-source Go projects and generates production-quality fixes. Uses LLMs via [OpenRouter](https://openrouter.ai/) (OpenAI-compatible API).

## How It Works

```
LOCALIZE (deterministic) → EXPLORE → PLAN → APPLY → REVIEW
                                       ↑                 │
                                       └── retry if NOT FIXED
```

1. **LOCALIZE** — Deterministically extracts repo context (zero LLM calls): repo tree, function signatures, keyword-ranked files, related tests, key function bodies
2. **EXPLORE** — LLM uses read-only tools (search, read, list, find symbol) to understand the issue and codebase
3. **PLAN** — LLM produces a precise edit plan (no tools, pure thinking): file paths, exact old_str/new_str for each change
4. **APPLY** — LLM executes the plan using edit_file and run_validation tools
5. **REVIEW** — LLM reviews the patch against the issue, responds FIXED or NOT FIXED
6. **Retry** — If NOT FIXED, loops back to PLAN → APPLY → REVIEW (max 2 retries)
7. **Output** — Generates patch diff, PR title/body, run summary, and trace log

## Architecture

```
agent/
├── __init__.py     # Package version
├── __main__.py     # Entry point (python -m agent)
├── cli.py          # CLI with run + compare subcommands
├── config.py       # Builds AgentConfig from CLI args and env vars
├── types.py        # Data structures (AgentConfig, Issue, ToolResult, RunSummary)
├── github.py       # GitHub API client (fetch issues, PR diffs, metadata)
├── repo.py         # Git operations (clone, checkout, branch, diff, commit)
├── tools.py        # 6 agent tools + phase-based tool gating
├── prompts.py      # Phase-specific prompts (explore, plan, apply, review, PR, compare)
├── localizer.py    # Deterministic repo localization (zero LLM calls)
├── logging_.py     # JSONL trace logger + token budget tracker
├── loop.py         # Multi-phase agent loop with retry
└── compare.py      # Compare agent diff against accepted PR
```

## Agent Tools

| Tool | Phase | Purpose |
|------|-------|---------|
| `search_code` | EXPLORE | Ripgrep-powered code search with optional glob filters |
| `read_file` | EXPLORE, APPLY | Read files with line numbers and optional line range |
| `list_dir` | EXPLORE | List directory contents to understand project structure |
| `find_symbol` | EXPLORE | Find Go symbol definitions and usages (func, type, var, const) |
| `edit_file` | APPLY | Precise find-and-replace edits (must match exactly once) |
| `run_validation` | APPLY | Full Go validation pipeline (gofmt, build, vet, test, lint) |

Tools are gated per phase — EXPLORE only gets read-only tools, APPLY only gets edit tools. PLAN and REVIEW get no tools (pure thinking).

## Prerequisites

- Python 3.10+
- Go toolchain (`go`, `gofmt`)
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`)
- [OpenRouter](https://openrouter.ai/) API key

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

## Usage

```bash
source .venv/bin/activate

# Solve an issue
python -m agent run --repo go-playground/validator --issue 1550

# Compare agent output against an accepted PR
python -m agent compare --repo go-playground/validator --issue 1550 --pr 1551

# Use a different model
python -m agent run --repo go-playground/validator --issue 1550 --model anthropic/claude-sonnet-4-5
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model` | `deepseek/deepseek-v4-pro` | OpenRouter model (one model for all phases) |
| `max_iterations` | `6` | Max iterations per phase |
| `max_tokens_total` | `200,000` | Token budget (tracked, not enforced) |
| `temperature` | `0.0` | LLM randomness (deterministic) |
| `workdir` | `workspace/` | Directory for cloned repos |
| `output_dir` | `runs/` | Directory for run outputs |

Any model on OpenRouter can be used via `--model` flag or `AGENT_MODEL` env var.

## Output

Each run saves to `runs/{repo}_issue{number}_{timestamp}/`:

| File | Contents |
|------|----------|
| `patch.diff` | Git diff of all changes |
| `PR.md` | Generated PR title and body |
| `summary.md` | Run stats (phases, iterations, tokens, tools, validation) |
| `trace.jsonl` | Full event log (API calls, tool calls, phase transitions) |
| `comparison.md` | Agent vs accepted PR analysis (from `compare` command) |

## Sample Results

Tested on `go-playground/validator` issues:

| Issue | Description | Result | Tokens |
|-------|-------------|--------|--------|
| #1550 | UUID validation fails for uppercase | **FIXED** | ~370K |
| #1481 | Numeric arrays pass string validations | NOT FIXED | ~3.4M |

Issue #1550 (regex fix) passes consistently. Issue #1481 (Go reflection type checking) is too complex for the current model — requires understanding `traverseField` internals.

## What Works

- Multi-phase loop with structural phase transitions (LOCALIZE → EXPLORE → PLAN → APPLY → REVIEW)
- Deterministic localization extracts repo context in zero LLM calls
- Phase-based tool gating prevents the LLM from exploring during APPLY
- Review phase with retry loop catches incorrect patches
- 6 agent tools with error handling and output truncation
- Sequential Go validation pipeline with fail-fast behavior
- Comparison against accepted PRs for quality evaluation
- JSONL trace logging for full observability

## What's Incomplete

- No unit tests (time constraint)
- No caching of cloned repos between runs
- AI_LOG.md could be more detailed

## What I'd Improve With More Time

- **Stronger model for hard issues** — Claude Sonnet or GPT-5.4 for complex Go reflection/type system bugs
- **Multi-patch sampling** — generate multiple independent patches at different temperatures, test each, pick the one that passes (Agentless-style)
- **Repo caching** — avoid re-cloning on repeated runs of the same repo
- **Streaming output** — show LLM responses in real-time
- **Context trimming between retries** — summarize failed attempts instead of carrying full history
- **Pre-fill old_str** — use the localizer to identify exact code spans, so the LLM only needs to write the replacement (Moatless-style)
