# ADR-0001: Agent Tribunal Model Selection

Date: 2026-10-07
Status: Proposed (finalizing as probe data completes)

## Context

The QtTune Agent Tribunal requires two local agents (code reviewer, automotive
engineer) running on Ollama against an RTX 3060 12GB. A third role
(interview coach) runs on a hosted model and is out of scope here.

## Candidates Considered

| Model | Disk | Residency | Throughput | Disposition |
|-------|------|-----------|------------|-------------|
| laguna-xs-2.1 (33B-A3B MoE) | 20 GB | 50/50 CPU/GPU | 63.9 tok/s | Selected: code reviewer |
| gemma4:12b (dense) | 8 GB | 100% GPU | 72.1 tok/s | Selected: automotive engineer |
| qwen3.8 (27B) | 17 GB | 52/48 CPU/GPU | 9.2 tok/s | Eliminated: throughput; retained as offline cross-check |

Culled before testing: qwen2.5-coder:14b (two generations stale);
deepseek-v4.1-flash, glm-5.3, kimi-k3 (cloud-routed only, not local weights).

## Decision

- Code reviewer: laguna-xs-2.1, scoped system prompt (v2-header-scope),
  num_ctx 32768.
- Automotive engineer: gemma4:12b, rubric test pending.
- Verdict derivation: judge derives merge verdicts from agent content
  (blockers/questions), never from the model's self-reported verdict label,
  which exhibits run-to-run jitter (approve <-> conditional with equivalent
  output). Parse failure fails closed.

## Evidence & Remediation Log

1. Fixture bug #1: clean-case test snippet lacked include guards; two models
   "falsely" flagged it — model dissent exposed eval ground-truth error.
2. Fixture bug #2: wrong namespace (qtune vs qttune) caused a spurious
   "Qt leakage" false positive.
3. Metric conflation: FP probe scored hedged questions and verdict-label
   inflation identically to fabricated violations. Resolved with a
   blockers/questions/nits taxonomy + derived verdicts.
4. Truncation failures: done_reason=length, eval_count≈6806 at num_ctx 8192 —
   thinking tokens consumed the output budget. Fixed: num_ctx 32768.
5. Probe crash: unhandled JSONDecodeError aborted a 5-run probe at run 3.
   Fixed: retry loop with failure metadata capture.

## Reviewer Validation (core.h, prompt v2, num_ctx 16384)

| Metric | Result |
|--------|--------|
| Blocker-FP rate | 0/5 (0%) |
| Verdict distribution | 1 approve / 4 conditional / 0 reject |
| Median questions | 5 per run |
| Parse failures | 0/5 (0%) |
| Timeouts | 0/5 (0%) |
| Per-run latency | ~90–180s (varied by thinking token volume) |

**Conclusion:** Laguna-xs-2.1 cleared the reviewer bar with the scoped prompt.
Behavioral stability is high (0 blockers, 0 verdict inflation). The 4/5
conditional verdicts reflect honest uncertainty flagged as questions, not
fabricated violations. Timeout reduction from 600→300s was premature; the
600s baseline from probe data is correct for production orchestrator.

## Bake-Off Results (v3-engineer-added prompt, 2026-10-07)

| Model | Bugs Detected | False Positives | JSON Fails | Avg Latency | Verdict |
|-------|---------------|-----------------|------------|-------------|---------|
| laguna-xs-2.1 | 5/5 | 0/1 | 0/6 | 26.9s | ✅ Reviewer slot |
| gemma4:12b | 5/5 | 0/1 | 0/6 | 24.0s | ✅ Domain expert |

**Qualitative difference:** Laguna cites line-plus-rule with fuller context
(e.g., "`#include <vector>` violates C ABI integrity" vs. just "`std::vector` used").
Gemma4 is terser but equally correct. Both survived scoped-prompt regime on
interface and implementation fixtures.

**Conclusion:** Two independently validated agents; neither dominated numerically.
Laguna retained as reviewer for thoroughness; gemma4 to domain expert role.
Both at v3 prompt version (namespace-correct, include-guard-fixed fixtures).

## Consequences

- Partial CPU offload (laguna) accepted: MoE active params (~3B) keep
  throughput at 63.9 tok/s despite 50% split.
- Thinking models pay per-call latency (~15-25s); a 3-round debate ≈ 2 min.
- Single-run eval results are anecdotes; all conclusions herein are based
  on multi-run aggregates. Eval harness bugs were themselves caught by
  repeated model disagreement and fixed — harness versioned via
  PROMPT_VERSION.

## Model Provenance

| Model | Ollama tag | Digest (ollama list) | Recorded |
|-------|------------|----------------------|----------|
| laguna-xs-2.1 | laguna-xs-2.1:latest | 0175be1e57f4 | 2026-10-07 |
| gemma4:12b | gemma4:12b | 6114515d63c1 | 2026-10-07 |

Unpinned `:latest` tags can silently re-point, invalidating eval numbers.
Re-verify with `ollama list` if reproducing results.

## Production Debate Example

Decision record: `coach_artifacts/decision_debate_20261007_194320.json`

Summary: Core ABI header review, 3 rounds, 0 blockers total, 6 engineer concerns.
Final verdict: MAX_ROUNDS_EXCEEDED (engineer raised unresolved architectural questions).

Interpretation: Code is merge-ready (no blockers), but the domain expert identified
follow-up work (timestamp source specification, transport URI schema). The tribunal
refused to auto-approve over unresolved concerns — by design, these are "manual review"
items, not bugs. Follow up: add a GitHub issue for timestamp/tunnel-uri spec.

Takeaway: The system correctly distinguishes "must-fix blockers" from
"nice-to-have clarifications" and doesn't rubber-stamp pending decisions.