# ADR-0001: Agent Tribunal Model Selection

Date: 2026-10-07
Status: Accepted; superseded in part by FP-reduction v1 (see Remediation
section) — reviewer validated on fixtures at 0% FP, revalidated in
production at 1/12 precision, remediated, re-measurement pending.

## Context

The QtTune Agent Tribunal requires two local agents (code reviewer, automotive
engineer) running on Ollama against an RTX 3060 12GB. A third role runs on a hosted model and is out of scope here.

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
  num_ctx 16384 (initially raised to 32768 to eliminate done_reason=length
  truncation from thinking tokens; validated back down to 16384 by probe —
  sufficient headroom with materially better latency).
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

## Diff-Based Review (2026-10-07)

Decision record: coach_artifacts/decision_debate_20261007_203917.json
Input: docs/fixtures/qttune_bridge_refactor.diff (real refactor between e0c4c31..8ffbf19)

Result: 12 blockers across 3 rounds, MAX_ROUNDS_EXCEEDED, fail-closed verdict.

Post-hoc triage against the actual QtTune source resolved every disputed
blocker (see triage notes below). Precision: 1 confirmed defect of 12
blockers (~8%) — versus 0/5 false positives on the clean-header probe.
This fixture-vs-production gap is the central eval finding of the project:
synthetic-fixture success did not transfer to real workloads.

## Blocker Triage (real refactor, post-debate)

Each of the 12 blockers was verified against the actual QtTune source:

| Class | Count | Examples | Disposition |
|---|---|---|---|
| Layer-rule misapplication | 7 | Qt-header includes in qttunebridge.h/.cpp | False positives: bridge is app-layer; CMake enforces no-Qt in qttune-core (FATAL_ERROR on Qt6::Core) |
| Definition-context guessing | 3 | "frame->data may reference freed stack memory"; anon-struct ABI worry | False positives: qttune_frame_t has inline uint8_t data[64], so the struct copy is a deep copy; anon typedef is legal C, defined once in core.h |
| Pedantic over-promotion | 1 | m_lastReportedDropped non-atomic | False positive: GUI-thread-only pairing with atomic m_droppedFrames is the correct pattern |
| Real defect | 1 | qttune_decode_signal(..., 8, ...) ignores frame->data_length | **Confirmed bug** — latent under mock transport (always 8 bytes), breaks for CAN-FD variable-length payloads. Fixed in QtTune |

Notes: the thread-safety and shared-state blockers all collapsed — access
is single-threaded by construction (queued connections to the GUI thread).
Issues the review MISSED (found by source-level triage): dropped-frame
report starvation under saturation, and last-write-wins in the staging
buffer coalescing path.

Key diagnostic: in round 2, the reviewer asked "What is the exact
structure of qttune_frame_t?" in its questions channel while filing a
stack-memory-use blocker. The model's epistemic state was correct —
uncertain — but the taxonomy discipline failed: hedged speculation was
promoted to a demonstrable-violation claim. This motivated the hedge
guardrail.

## Remediation: False-Positive Reduction v1 (2026-10-07)

Two of three failure classes remediated, both as deterministic guardrails
(model output filtered through rule-based code, not prompt pleas):

1. **Hedge demotion** (class: speculative phrasing) — blockers whose text
   contains hedge language ("may", "might", "could", "appears to",
   "needs verification") are demoted to the questions channel before
   judging. Implemented as HEDGE_PATTERNS regex +
   demote_hedged_blockers(). Regression-tested against production-derived
   blocker texts: 7 unit cases, 6/6 demote-or-not expectations met,
   runnable without any LLM.

   Boundary (deliberate): this catches *phrased-as-speculation* claims
   only. Confidently stated assertions — including wrong ones — pass
   through. Verified experimentally: a model confidently flagging a
   race condition documented in the code's own comment was correctly
   NOT demoted. Fixing the confident-wrong class requires information,
   not rhetoric filtering (see remediation #3).

2. **Layer metadata injection** (class: layer misapplication) —
   file_metadata.py maps file paths to QtTune layers (core/bridge/app);
   the transcript now states which rules apply. Bridge-layer Qt includes
   are pre-legitimized in-prompt.

3. **Definition-context injection** (class: confident guessing) — OPEN.
   When a diff references types whose definitions live elsewhere
   (qttune_frame_t et al.), inject the typedef as ground truth.
   Queued; see STATUS.md.

**Re-measurement pending:** rerun the bridge-refactor diff debate and
compare blocker precision against the 1/12 baseline. Same fixture
(docs/fixtures/qttune_bridge_refactor.diff) for comparability.

## Golden Suite Composition (post-v1)

10/10: 3 LLM-backed model fixtures + 7 deterministic guardrail
regression tests. The deterministic subset requires no Ollama and is
CI-suitable.
