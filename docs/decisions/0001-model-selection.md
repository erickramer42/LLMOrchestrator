# ADR-0001: Agent Tribunal Model Selection

Date: 2026-10-07
Status: Accepted

Adjudication and false-positive remediation decisions live in
[ADR-0002](0002-adjudication-and-fp-remediation.md).

## Context

The QtTune Agent Tribunal requires two local agents (code reviewer, automotive
engineer) running on Ollama against an RTX 3060 12GB. A third role runs on a
hosted model and is out of scope here.

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
- Automotive engineer: gemma4:12b.
- Verdicts are derived from agent content (blockers/questions), never from
  the model's self-reported verdict label — see ADR-0002.

## Evaluation Evidence

Model dissent repeatedly exposed defects in the eval harness itself before
questioning the models — documented here because it shaped how much the
numbers below can be trusted:

1. Fixture bug #1: clean-case snippet lacked include guards; two models
   "falsely" flagged it — ground-truth error, not model error.
2. Fixture bug #2: wrong namespace (qtune vs qttune) caused a spurious
   Qt-leakage false positive.
3. Metric conflation: FP probe scored hedged questions and verdict-label
   inflation identically to fabricated violations. Resolved with a
   blockers/questions/nits taxonomy + derived verdicts.
4. Truncation: done_reason=length at num_ctx 8192 (thinking tokens consumed
   the output budget). Fixed via context increase.
5. Probe crash: unhandled JSONDecodeError aborted a 5-run probe at run 3.
   Fixed with retry loop + failure metadata capture.

### Reviewer Validation (core.h, prompt v2, num_ctx 16384)

| Metric | Result |
|--------|--------|
| Blocker-FP rate | 0/5 (0%) |
| Verdict distribution | 1 approve / 4 conditional / 0 reject |
| Median questions | 5 per run |
| Parse failures | 0/5 (0%) |
| Timeouts | 0/5 (0%) |
| Per-run latency | ~90–180s |

### Bake-Off Results (v3-engineer-added prompt, 2026-10-07)

| Model | Bugs Detected | False Positives | JSON Fails | Avg Latency | Verdict |
|-------|---------------|-----------------|------------|-------------|---------|
| laguna-xs-2.1 | 5/5 | 0/1 | 0/6 | 26.9s | Reviewer slot |
| gemma4:12b | 5/5 | 0/1 | 0/6 | 24.0s | Domain expert |

**Qualitative difference:** Laguna cites line-plus-rule with fuller
context (e.g., "#include <vector> violates C ABI integrity" vs. just
"std::vector used"). Gemma4 is terser but equally correct.

## Consequences

- Partial CPU offload (laguna) accepted: MoE active params (~3B) keep
  throughput at 63.9 tok/s despite 50% split.
- Thinking models pay per-call latency (~15-25s); a 3-round debate ≈ 2 min.
- Fixture-validation numbers (0% FP) did NOT transfer to production
  workloads — measured at 1/12 precision on the first real diff. That
  finding and its remediation are the subject of ADR-0002.

## Model Provenance

| Model | Ollama tag | Digest | Recorded |
|-------|------------|--------|----------|
| laguna-xs-2.1 | laguna-xs-2.1:latest | 0175be1e57f4 | 2026-10-07 |
| gemma4:12b | gemma4:12b | 6114515d63c1 | 2026-10-07 |

Unpinned `:latest` tags can silently re-point, invalidating eval numbers.
Re-verify with `ollama list` if reproducing results.
