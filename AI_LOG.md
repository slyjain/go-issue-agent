# AI Log

Significant AI interactions during development — what I asked, what came back, what I kept/modified/rejected.

### 1. Initial architecture from reference project
**Asked:** How to structure an agentic AI system for fixing Go issues, referencing a previous implementation (PocketFmAssignment).
**Came back:** File-by-file implementation plan with 14 phases, mapping each module from the reference.
**Kept:** The overall structure (types.py, github.py, repo.py, tools.py, prompts.py, loop.py, cli.py, config.py, logging_.py, compare.py). Adapted it rather than copying — switched from Anthropic SDK to OpenAI SDK for OpenRouter compatibility.

### 2. Single loop fails — agent never edits
**Asked:** Why does the agent spend all 12 iterations searching/reading and never call edit_file?
**Came back:** Root cause analysis — no structural forcing to transition phases, message history grows unbounded, system prompt says "understand BEFORE editing" but never forces a stop.
**Kept:** The diagnosis. Led to the multi-phase loop design (EXPLORE → PLAN → APPLY).

### 3. Multi-phase loop design
**Asked:** Design a loop with explicit phases — EXPLORE (read-only tools), PLAN (no tools), APPLY (edit tools).
**Came back:** Detailed plan with phase-specific prompts, tool gating via `get_tools_for_phase()`, forced summary nudge if EXPLORE hits iteration limit.
**Kept:** Everything. This was the key architectural improvement. First test on #1550 produced a correct UUID fix.

### 4. Dual-model strategy (tried and reverted)
**Asked:** Can we use a cheap model (Flash) for tool-calling and a smarter model (Pro) for thinking?
**Came back:** Implementation with `model` for EXPLORE/APPLY and `plan_model` for PLAN/REVIEW.
**Rejected:** Flash (13B params) was too weak for APPLY — it could search but never produced edit_file calls on complex issues. Reverted to single Pro model for all phases.

### 5. Multi-patch sampling (tried and reverted)
**Asked:** Implement Agentless-style multi-patch sampling — 5 independent patches at different temperatures, test each.
**Came back:** Full implementation with `_git_reset`, `_git_apply_diff`, `_run_go_test` helpers and fresh messages per patch.
**Rejected:** With Flash model, all 5 patches produced zero edits. The bottleneck was model capability, not architecture diversity. Removed in favor of simpler retry loop with Pro model.

### 6. Research — what other projects do
**Asked:** Search the web for architectures used by other AI coding agents.
**Came back:** Analysis of Agentless (hierarchical localization, no agents), SWE-agent (custom ACI, sliding window), Moatless (finite state machine, pre-filled old_str), OpenDevin (multi-agent delegation).
**Kept:** The key insight from Agentless — deterministic localization beats LLM-driven exploration. Implemented as the LOCALIZE phase.

### 7. Deterministic LOCALIZE phase
**Asked:** How to extract repo context without LLM calls.
**Came back:** Five extraction steps: repo tree, file skeletons (grep for func/type declarations), keyword localization (rg -c per keyword), related tests, key function bodies.
**Kept:** All five steps. Implemented in `localizer.py`. On #1550, it found `isUUID3/4/5` in `baked_in.go` deterministically — exactly what the LLM spent 60K tokens discovering.

### 8. REVIEW phase + retry loop
**Asked:** Add a review phase that checks if the patch actually fixes the issue.
**Came back:** REVIEW with `VERDICT: FIXED` / `VERDICT: NOT FIXED` format, retry loop that goes back to PLAN if not fixed.
**Kept:** The full design. Review correctly identified unfixed patches and triggered retries.

### 9. Model selection and pricing
**Asked:** List coding models on OpenRouter with pricing.
**Came back:** 16 models from $0.04/M to $30/M with context windows and capabilities.
**Modified:** Started with Claude Sonnet ($3/$15), switched to DeepSeek V4 Pro ($0.44/$0.87) for cost. Flash ($0.10/$0.20) was too weak. Pro is the sweet spot for this use case.
