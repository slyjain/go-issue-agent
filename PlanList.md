# Plans Made During Development

---

## Plan 1: Original Architecture (misty-scribbling-lynx)

### Context
Building a take-home assignment: an agentic AI system that takes a GitHub issue from a Go project and produces a code change that fixes it. Graded on 5 axes: (1) right files, (2) relevant changes, (3) project conventions, (4) validation, (5) PR summary.

### Language Decision
**Python 3.11+** for orchestration. Go toolchain is shelled out to. Only external dependency: `anthropic` SDK (later switched to `openai` for OpenRouter compatibility).

### Candidate Test Issues (go-playground/validator)

| # | Issue | PR | Files Changed | Why Good |
|---|-------|----|---------------|----------|
| 1 | **#1550** — UUID validation fails for uppercase | #1551 | 2 (regexes.go, validator_test.go) | Single regex fix, minimal scope |
| 2 | **#1576** — Cron validator accepts arbitrary strings | #1577 | 2 (regexes.go, validator_test.go) | Regex anchor fix, 18 test cases added |
| 3 | **#1481** — Numeric arrays pass string validations | #1498 | 2 (baked_in.go, validator_test.go) | Type-checking logic fix, labeled "good first issue" |

### Package Structure
```
agent/
├── __init__.py          # Version constant
├── __main__.py          # Entry: from agent.cli import main; main()
├── cli.py               # argparse: run + compare subcommands
├── config.py            # AgentConfig from CLI args + env
├── types.py             # Shared dataclasses: Issue, ToolResult, RunSummary
├── github.py            # fetch_issue, fetch_pr_diff via urllib
├── repo.py              # clone_repo, checkout_commit, get_diff
├── tools.py             # 6 tool schemas + execution functions
├── prompts.py           # System prompt + PR generation prompt
├── loop.py              # Core agent loop
├── logging_.py          # JSONL trace logger + token tracker
└── compare.py           # Compare agent output vs accepted PR
```

### Core Loop Design
```python
while iteration < max_iterations and not token_tracker.exceeded():
    response = client.messages.create(model=..., tools=TOOL_DEFINITIONS, messages=messages)
    if response.stop_reason != "tool_use":
        break  # Agent says it's done
    tool_results = [execute_tool(block) for block in tool_calls]
    messages.append(tool_results)
```

### Key Design Decisions
1. No RAG/embeddings — repos are small, ripgrep is fast enough
2. Temperature 0.0 — deterministic, reproducible runs
3. edit_file requires unique match — prevents ambiguous edits
4. urllib.request, not requests — no extra dependency
5. Validation cascade with skip-on-failure — most actionable error first
6. Separate PR generation call — clean output
7. Outputs patch.diff + PR.md to disk — user decides what to apply

---

## Plan 2: Multi-Phase Loop (dapper-sniffing-knuth)

### Problem
The single-loop design failed — the LLM spent ALL iterations searching/reading and never got to editing. In a 12-iteration run on validator#1550, it made 19 tool calls — all `search_code` or `read_file`, zero `edit_file`. Context grew from 2,316 to 7,447 tokens per call.

### Root Cause
No structural forcing to transition from exploring to editing. Message history grows unbounded. The prompt says "understand BEFORE editing" but never says "stop exploring now."

### Solution: Three Explicit Phases

```
Phase 1: EXPLORE (Flash model, max 6 iters)
  Tools: search_code, read_file, list_dir, find_symbol
  Output: exploration summary text
      ↓ (phase marker injected into shared conversation)
Phase 2: PLAN (Pro model, 1 call, no tools)
  Input: issue + all exploration context
  Output: concrete edit plan (file, old_str, new_str for each change)
      ↓ (phase marker injected)
Phase 3: APPLY (Flash model, max 10 iters)
  Tools: edit_file, run_validation, read_file
  Input: plan + all previous context
  Output: edited files + validation
```

### Key Design Changes
- **One shared `messages` list** across all phases — context carries forward
- **Phase markers** injected as user messages (`=== PHASE 2: PLAN ===`)
- **Tool gating** per phase via `get_tools_for_phase()`
- **Dual-model strategy**: cheap Flash for tool-calling, smarter Pro for thinking
- **Forced summary nudge** if EXPLORE hits iteration limit without producing text

### Dual-Model Cost Strategy

| Phase | Model | Cost |
|-------|-------|------|
| EXPLORE | deepseek/deepseek-v4-flash | $0.10/$0.20 per M tokens |
| PLAN | deepseek/deepseek-v4-pro | $0.44/$0.87 per M tokens |
| APPLY | deepseek/deepseek-v4-flash | $0.10/$0.20 per M tokens |
| PR gen | deepseek/deepseek-v4-pro | $0.44/$0.87 per M tokens |

~$0.04 per run vs ~$0.10 with all-Pro vs ~$1-2 with Claude Sonnet.

### First Test Result (validator#1550)
- Agent correctly changed `[0-9a-f]` to `[0-9a-fA-F]` in UUID regexes
- 3 files edited (regexes.go UUID3, UUID4, UUID5)
- Generated correct PR description
- Hit token budget (200K) due to DeepSeek calling non-existent tools

---

## Plan 3: Add REVIEW Phase + Retry Loop (dapper-sniffing-knuth v2)

### Problem
After the multi-phase loop was working, two issues remained:
1. No review — the agent doesn't check if its patch actually fixes the issue
2. Strict token budget (200K) and iteration caps cause premature termination

### Solution: REVIEW Phase + Retry Loop

```
EXPLORE (Flash, 8 iters) → PLAN (Pro, 1 call) → APPLY (Flash, 15 iters) → REVIEW (Pro, 1 call)
                                    ↑                                            │
                                    └──── if review says "NOT FIXED" ────────────┘
                                          (max 2 retries)
```

### REVIEW Phase Design
- Uses Pro model (needs reasoning to evaluate correctness)
- Gets the issue + the diff of changes
- Responds with `VERDICT: FIXED` or `VERDICT: NOT FIXED` + explanation
- If NOT FIXED, injects feedback and loops back to PLAN → APPLY → REVIEW

### Relaxed Limits
- Remove strict token budget check (keep tracking, don't stop the run)
- Increase iteration caps: EXPLORE 8, APPLY 15
- Max 2 retries of the PLAN → APPLY → REVIEW cycle

### Retry Loop Structure
```python
# EXPLORE runs once (outside retry loop)
for retry in range(MAX_RETRIES + 1):
    # PLAN → APPLY → REVIEW
    if "VERDICT: FIXED" in review_text:
        break
    # NOT FIXED — inject feedback, loop back to PLAN
```

EXPLORE stays outside because codebase understanding doesn't change. Only the fix strategy needs revision.

### Changes Required
1. `prompts.py` — add `build_review_prompt(issue, diff)`
2. `loop.py` — add REVIEW phase, retry loop, remove strict budget check, increase caps
3. `types.py` — no changes (phases_completed list handles repeated phases)

---

## Plan 4: LOCALIZE Phase — Deterministic Context Extraction (Zero LLM Calls)

### Problem
The EXPLORE phase uses 8 LLM iterations to search/read files — costing ~60K tokens. On complex issues (#1481), the LLM wastes iterations searching randomly. Research (Agentless, SWE-bench SOTA) proved that deterministic localization outperforms free-form agent exploration.

### Solution
Add a LOCALIZE phase (Phase 0) before EXPLORE. Pure Python — subprocess + file I/O. Zero LLM calls. Extracts 5 types of context:

1. **Repo tree** — `os.walk`, all `.go` files with line counts
2. **File skeletons** — `grep '^func \|^type '` on all Go files, declarations only
3. **Keyword localization** — extract keywords from issue, `rg -c` each keyword, rank files by hits
4. **Related tests** — `rg 'func Test.*keyword'` in test files
5. **Key functions** — read actual function bodies matching keywords from top-ranked files (max 3 functions, 50 lines each)

### Architecture
```
LOCALIZE (0 LLM calls) → EXPLORE (Flash, 8 iters) → PLAN (Pro) → APPLY (Flash) → REVIEW (Pro)
```

Context from LOCALIZE is injected into the first user message. EXPLORE starts with full repo knowledge instead of searching blindly.

### Implementation
- New file: `agent/localizer.py` (~150 lines)
- Modified: `agent/loop.py` — add LOCALIZE call before EXPLORE, inject context into messages
- No other files changed

### Key Insight
For issue #1550 (UUID uppercase), the localizer deterministically found `isUUID3`, `isUUID4`, `isUUID5` in `baked_in.go` and ranked it as the #2 most relevant file — exactly what the LLM spent 6 iterations discovering. Cost: 0 tokens vs 60K tokens.

---

## Plan 5: Multi-Patch Sampling (Agentless-inspired)

### Problem
The retry loop shows the LLM its own failed attempts, causing it to repeat similar mistakes. On #1481, all 3 retries failed spending 3.4M tokens ($1.50). Each retry saw the previous failure and thought similarly.

### Solution
Replace retry loop with multi-patch sampling. Generate 5 independent patches (fresh conversation each), run `go test` on each, pick the first that passes.

### Architecture
```
LOCALIZE → EXPLORE → PLAN → Generate 5 patches independently → Test each → Pick best → REVIEW → PR
```

### How It Works
1. After PLAN produces a plan, generate 5 patches:
   - Patch 1: temperature 0.0 (deterministic best guess)
   - Patches 2-5: temperature 0.7 (creative alternatives)
2. Each patch gets a **fresh `messages` list** — no cross-contamination
3. After all patches generated, `git reset` between each
4. Apply each patch and run `go test ./...`
5. First patch that passes tests wins
6. If none pass, use the first patch (best effort)
7. REVIEW phase evaluates the winning patch

### Why This Is Better
- **Independent attempts** — each patch doesn't see others' failures
- **Tests decide** — not the LLM reviewing itself
- **Fresh context** — each attempt starts with ~2K tokens, not 90K+
- **Diversity** — temperature 0.7 explores different fix strategies
- **Cheaper** — 5 fresh calls < 3 retries with growing context

### Changes
1. `loop.py` — replace retry loop with multi-patch sampling + `_git_reset`, `_git_apply_diff`, `_run_go_test` helpers
2. `DECISIONS.md` — add multi-patch sampling decision

### Outcome
Tried and reverted. Flash model produced 0 edits across all 5 patches. Bottleneck was model capability, not architecture.

---

## Plan 6: Simplify to Single Model + Final Cleanup

### Problem
Dual-model (Flash+Pro) and multi-patch sampling both failed on complex issues because Flash (13B params) can't reason about Go reflection/type systems. Complexity added for no gain.

### Solution
Simplify everything:
- One model (`deepseek/deepseek-v4-pro`) for all phases
- Remove `plan_model` from AgentConfig
- Remove multi-patch sampling, revert to retry loop
- Keep LOCALIZE (deterministic, proven useful)
- Keep REVIEW + retry loop (proven useful on #1550)

### Final Architecture
```
LOCALIZE (0 LLM) → EXPLORE (Pro) → PLAN (Pro) → APPLY (Pro) → REVIEW (Pro)
                                        ↑                           │
                                        └── retry if NOT FIXED ─────┘
```

### Cleanup
- README.md rewritten to match final architecture
- AI_LOG.md filled with 9 entries
- runs/ pruned to 2 best sample runs
- DECISIONS.md updated with all final decisions
- All stale references (plan_model, Flash, multi-patch) removed
