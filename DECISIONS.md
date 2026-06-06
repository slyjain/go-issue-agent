# Decisions

### Why OpenRouter instead of Anthropic directly?
OpenRouter gives access to multiple models (Claude, GPT, Gemini, DeepSeek) through one API key and one interface. If one model is down or expensive, we can switch by changing a single string. It uses the OpenAI-compatible API format, so no vendor lock-in.

### Why DeepSeek V4 Pro as the default model?
We evaluated models on OpenRouter by cost and coding ability. DeepSeek V4 Pro hits the sweet spot — strong coding performance at $0.44/$0.87 per million tokens. With a $9.24 OpenRouter budget, that's ~50 agent runs vs ~5 with Claude Sonnet ($3/$15).

| Model | Context | Input $/M | Output $/M | Notes |
|-------|---------|-----------|------------|-------|
| qwen/qwen3.5-9b | 262K | $0.04 | $0.15 | Tiny 9B params, cheapest |
| deepseek/deepseek-v4-flash | 1M | $0.10 | $0.20 | MoE 13B active, fast |
| tencent/hy3-preview | 262K | $0.06 | $0.21 | Configurable reasoning |
| mistralai/mistral-small-2603 | 262K | $0.15 | $0.60 | Multimodal, budget |
| deepseek/deepseek-v4-pro | 1M | $0.44 | $0.87 | **Default — 49B active, best value** |
| openai/gpt-5.4-nano | 400K | $0.20 | $1.25 | Lightweight, fast |
| qwen/qwen3.7-plus | 1M | $0.40 | $1.60 | Multimodal, mid-range |
| x-ai/grok-4.3 | 1M | $1.25 | $2.50 | Reasoning, agentic |
| qwen/qwen3.7-max | 1M | $1.25 | $3.75 | Flagship, agent-centric |
| openai/gpt-5.4-mini | 400K | $0.75 | $4.50 | Reasoning + coding |
| mistralai/mistral-medium-3.5 | 262K | $1.50 | $7.50 | 128B dense, complex tasks |
| google/gemini-3.5-flash | 1M | $1.50 | $9.00 | Google, multimodal |
| openai/gpt-5.4 | 1M | $2.50 | $15.00 | Frontier |
| anthropic/claude-sonnet-4-5 | 1M | ~$3.00 | ~$15.00 | Best tool adherence |
| anthropic/claude-opus-4.8 | 1M | $5.00 | $25.00 | Deepest reasoning |
| openai/gpt-5.5 | 1M | $5.00 | $30.00 | Top tier |

All models support tool/function calling via OpenRouter.

**Key factors for choosing a model for this agent:**

1. **Tool adherence** — Does the model only call tools it's been given? DeepSeek tried calling `grep`, `bash`, `web_search` which don't exist. Claude and GPT strictly follow the provided tool schema.
2. **Cost per run** — A typical run uses ~40-60K tokens. At $0.44/$0.87 (DeepSeek V4 Pro) that's ~$0.05-0.10 per run. At $3/$15 (Claude Sonnet) it's ~$1-2 per run.
3. **Context window** — Not critical for this agent (each phase resets context to ~2-3K tokens), but 1M context helps if a single file is very large.
4. **Coding quality** — The model needs to understand Go, write correct regex, and produce valid `old_str`/`new_str` for find-and-replace edits.

### Why a multi-phase loop (EXPLORE → PLAN → APPLY) instead of a single loop?
In testing, a single loop with all tools available caused the LLM to spend all iterations searching/reading and never editing. In a 12-iteration run, it made 19 tool calls — all search_code or read_file, zero edit_file. The multi-phase approach forces structural transitions: explore with read-only tools, produce a plan with no tools, then apply with edit tools. Context resets between phases so each phase starts fresh instead of accumulating 7k+ tokens of history.

### Why ripgrep instead of grep or building a code index?
Ripgrep is fast enough for single-repo issues — it searches the entire go-playground/validator repo in under a second. Building an embedding index or AST-based search would add complexity (chunking, vector DB, re-indexing on edits) for no real gain on small/medium issues. If the agent needed to work on massive monorepos, indexing would make sense. Here it doesn't.

### Why find-and-replace edits instead of writing full files?
Find-and-replace forces the agent to be precise — it must specify exactly what to change. Full file writes risk accidentally deleting code, changing formatting, or introducing subtle bugs. The "must match exactly once" constraint catches ambiguous edits early.

### Why a local diff instead of opening a real PR?
The assignment says opening a PR is optional. A local diff is safer — it doesn't pollute open-source repos with test PRs, doesn't need GitHub auth tokens with write access, and the output is the same: a patch + PR description that can be reviewed.

### Why sequential validation (gofmt → build → vet → test) instead of parallel?
Each step depends on the previous one. There's no point running tests if the code doesn't compile, and no point running vet if build fails. Sequential with early exit saves time and gives the agent clear, actionable errors at each stage.

### Why no authentication for the GitHub API?
Unauthenticated GitHub API allows 60 requests/hour. For a single issue run (fetch issue, maybe fetch a PR for comparison), that's plenty. Adding a GitHub token would mean another secret to manage for zero practical benefit in this use case.

### Why `logging_.py` and not `logging.py`?
The underscore avoids shadowing Python's built-in `logging` module. If you named it `logging.py`, then `import logging` anywhere in the project would import your file instead of Python's stdlib — breaking everything.

### Why one model (Pro) for all phases instead of dual-model (Flash + Pro)?
We tried using Flash ($0.10/$0.20) for tool-calling phases (EXPLORE, APPLY) and Pro ($0.44/$0.87) for thinking (PLAN, REVIEW). Flash was too weak — on issue #1481 it spent 15 iterations reading files without ever calling edit_file. It can't understand Go reflection or produce correct find-and-replace edits for complex issues. Using Pro for everything costs more per run (~$0.10-0.20 vs ~$0.04) but actually produces working fixes.

### Why we tried and removed multi-patch sampling
We implemented Agentless-style multi-patch sampling: generate 5 independent patches at different temperatures, run `go test` on each, pick the first that passes. In theory this is better than a retry loop (no cross-contamination, tests decide instead of LLM self-review). In practice, with Flash model, all 5 patches produced zero edits because Flash couldn't reason about the fix even with full context. Multi-patch sampling works when the model is capable enough to produce edits — the bottleneck was model capability, not architecture. We reverted to a simpler retry loop with Pro model for all phases.

### Why deterministic LOCALIZE before LLM exploration?
The EXPLORE phase used to waste 6-8 LLM iterations just to discover which files are relevant. LOCALIZE extracts the same information in zero LLM calls using grep, ripgrep, and file I/O: repo tree, function signatures, keyword-ranked files, related tests, and key function bodies. On issue #1550, it deterministically found `isUUID3/4/5` in `baked_in.go` — exactly what the LLM spent 60K tokens discovering.