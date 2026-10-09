# STATUS — Project Map & Continuation Notes

Last updated: 2026-10-09 (v1 re-measurement complete; ADR-0002 added)

Purpose of this file: anyone picking up this repo can
orient in five minutes, run the existing validation, and continue the
queued work without reverse-engineering the ADRs.

---

## Current State

**Working and validated:**
- 3-round adversarial debate loop with rule-based judge
- Derived verdicts (content-based, not model self-report)
- Fail-closed parse/timeout handling with retry (temp fallback 0.05)
- Layer metadata injection (core / bridge / app)
- Hedge-language demotion guardrail (deterministic, regression-tested)
- Golden suite: 3 model fixtures + 7 deterministic guardrail units = 10/10
- FP-rate probe (5-run aggregates), model bake-off
- Module split (2026-10-08): single-file orchestrator decomposed into
  config / agent_client / adjudication / debate / golden_tests, with
  orchestrator.py reduced to a thin CLI entrypoint
- **False-positive reduction v1, measured twice:** baseline 1/12 blocker
  precision (2026-10-07, decision_debate_20261007_203917) → 1/6 after
  layer metadata + hedge demotion (2026-10-09,
  decision_debate_20261009_014257, same diff). Layer-class blockers:
  7 → 0. Hedge-class: 0, with 0 demotions fired (the reviewer stopped
  hedging; taxonomy discipline worked at the source). Full analysis
  in ADR-0002.
- **Feedback loop repair (2026-10-09):** transcript re-rendered per round
  so `REVISE ADDRESSING` feedback reaches agents; archived records read
  as multi-sample measurements; prompt version bumped to v4. Evidence:
  smoke debate (20261009_153541) shows engineer elevating concerns to
  blockers upon seeing prior critique.

**Known limitations (by design or pending):**
- Unresolved concerns/questions force MAX_ROUNDS_EXCEEDED → manual
  review. Intentional (fail-closed); convergence behavior may improve
  once context pack (backlog #1) supplies missing ground truth.
- **Confident-but-wrong assertions are now the dominant FP class**
  (4/6 blockers in the re-measurement: thread-safety claims on
  GUI-thread-only state). Hedge regex provably cannot touch these —
  the fix is ground-truth context (repo context pack, backlog #1).
- Diff-only review caps recall: both real bugs found by full-repo
  triage (drop-count starvation, staging-buffer last-write-wins) were
  invisible in the diff itself. Also addressed by the context pack.
- Multi-file diffs only inject the FIRST file's layer. Queued.
- Golden model fixtures are nondeterministic; guardrail units are not.
  CI should run the guardrail subset + compile checks, mocked or
  skipped LLM cases.

---

## File Map

| Path | Purpose |
|---|---|
| `orchestrator.py` | Thin CLI entrypoint: argument parsing and dispatch only. Re-exports key symbols (call_agent, MODELS, derive_verdict, demote_hedged_blockers) as a transition shim for older importers. |
| `config.py` | Central configuration: MODELS dict, num_ctx, timeouts, temperatures, and prompt composition (REVIEWER_IMPL_PROMPT / REVIEWER_HEADER_PROMPT). Single place to swap models. |
| `agent_client.py` | Ollama client. Single agent turn, JSON-mode enforcement, retry logic, FAILURE_SENTINEL emission. The ONLY module that touches the network. |
| `adjudication.py` | Pure adjudication logic, no I/O: `derive_verdict()` (content-based verdicts) and `demote_hedged_blockers()` (hedge regex guardrail). CI-importable with no model serving. |
| `debate.py` | The debate loop (fixed 2026-10-09: transcript re-rendered
per round so REVISE ADDRESSING feedback reaches agents; previously frozen
before the loop, making rounds 2–3 blind resamples). See erratum in ADR-0002.|
| `golden_tests.py` | Golden suite: 3 LLM-backed model fixtures + `run_hedge_unit_tests()` (7 deterministic guardrail regression cases, production-derived texts). |
| `reviewer_prompt.py` | Single source of truth for all prompts. PROMPT_VERSION stamped into decision records. REVIEWER_SYSTEM + IMPL_SCOPE_CLAUSE / HEADER_SCOPE_CLAUSE compose the two reviewer prompts. |
| `file_metadata.py` | File-path → layer mapping (core/bridge/app). `get_layer_constraints()` returns the injected transcript text telling the reviewer which rules apply. |
| `eval_harness/probe.py` | FP-rate probe: N runs against a clean fixture, aggregates blocker/verdict distribution, timeouts, parse failures. |
| `eval_harness/bakeoff.py` | Side-by-side model comparison on bug fixtures + clean fixture. |
| `eval_harness/__init__.py` | Package marker. |
| `docs/decisions/0001-model-selection.md` | ADR-0001: model selection rationale, bake-off numbers, eval harness bug history. THE document for "why these models on this hardware." |
| `docs/decisions/0002-adjudication-and-fp-remediation.md` | ADR-0002: the false-positive arc — 1/12 baseline triage, guardrail design, 1/6 re-measurement, residual class analysis. THE document for "why these guardrails." |
| `docs/portability_guide.md` | Running on other machines / codebases. |
| `docs/fixtures/qttune_bridge_refactor.diff` | Input diff for the bridge-refactor debates (baseline AND v1 re-measurement — same fixture enables comparability). Keep record/fixture pairs together. |
| `coach_artifacts/decision_debate_*.json` | Decision records: round history, hedge_demotions counts per round, verdict, metadata (prompt version, models). Three archived: header review (194320), baseline diff review (203917), v1 re-measurement (014257). Intended consumer: "coach agent" for human-facing synthesis. |
| `probe_logs/fp_*.json` | 5-run probe aggregates backing the FP-rate claims in the ADR. |
| `requirements.txt` | Runtime deps (requests only, as of this writing). |
| `.gitignore` | Note: `gold_tests/run_*.json` outputs are transient and NOT committed. Eval evidence lives in probe_logs/ and coach_artifacts/. |

**Module dependency direction (acyclic):** reviewer_prompt + file_metadata
(leaves) → config → agent_client and adjudication (parallel layers) →
debate + golden_tests → orchestrator (CLI handle).

---

## Conventions (do not silently violate)

1. **Derived verdicts only.** Never trust a model's self-reported
   verdict label. Judge reads blockers/questions/concerns arrays
   (adjudication.derive_verdict).
2. **Fail closed.** Parse failure, timeout, empty input → reject /
   manual review. Never default to approve. (Enforced in
   agent_client.call_agent + adjudication.)
3. **Blockers must be demonstrable.** Speculation belongs in questions.
   If you widen HEDGE_PATTERNS in adjudication.py, the 7 unit cases in
   `run_hedge_unit_tests()` (golden_tests.py) must still pass — several
   are negative controls that assert confident statements are NOT demoted.
4. **Prompts are versioned.** Any prompt change bumps PROMPT_VERSION in
   reviewer_prompt.py so eval results correlate to prompt revisions.
5. **Evidence pairs.** Every committed decision record needs its input
   fixture committed alongside (docs/fixtures/).
6. **Predict before measuring.** Write down the expected outcome before
   an eval run; record it in the ADR alongside results. Cheapest defense
   against post-hoc rationalization. (Practiced for the v1 re-measurement:
   prediction held on all three classes.)
7. **Quantify, then fix, then re-measure.** measure FP rate → root-cause
   classes → remediate → re-measure. Continue it.
8. **Respect the module boundaries.** Network calls only in
   agent_client.py; adjudication stays pure (no I/O) so it remains
   CI-testable. Don't let conveniences erode that.

---

## Backlog (ideas, loosely ordered)

Nothing here is committed to — loosely sorted by what unblocks what.

1. **Repo context pack** (subsumes definition-context injection; now the
   top priority since re-measurement confirmed confident-but-wrong as
   the dominant residual class). Offline indexer → repo_context.json
   (file purposes, type/constant registry, layer map); debate-time
   retrieval keyed on diff references; optional --repo-scan holistic
   mode. Ground truth for eval: 4 production findings from manual repo
   scan (coolant overflow, CI test gap, stale page number, doc test
   counts), 2026-10-08. When built: re-measure the bridge diff a third
   time — expect the 4 thread-safety FPs to collapse once queued-
   connection call sites are visible.
2. **Judge granularity rework.** Split severity from resolution:
   APPROVED / APPROVED_WITH_FOLLOWUPS / BLOCKED with severity-tagged
   follow-ups recorded in the decision record. Design first; current
   fail-closed behavior is defensible.
3. **GitHub Actions CI.** Compile checks + hedge units + judge logic,
   importing adjudication/golden_tests directly — no Ollama needed.
4. **Per-debate cost/latency telemetry.** Wall-clock per round and
   eval_count (token estimate) stamped into decision records.
5. **Cloud model support.** OpenAI-compatible endpoint in
   agent_client.py. Golden suite first (cost control); keep cloud
   results segregated in the ADR. Local-vs-cloud bake-off on the same
   fixtures would be a publishable comparison.
6. **Chained/escalated debates.** On MAX_ROUNDS_EXCEEDED, re-submit
   unresolved questions as a fresh debate (different model pair
   optional), depth capped at 2, parent_debate_id recorded. Depends
   on #2 — both touch termination logic.
7. **Stable real-diff corpus.** 3–5 triaged real diffs with known
   expected outcomes — the systemic answer to fixture-pass /
   production-fail.
8. **Multi-file diff layer handling.** Parse all `+++ b/` headers;
   inject a layer map keyed by file.
9. **Retire the orchestrator re-export shim** once eval_harness
   imports from agent_client/config directly.
10. **Codebase abstraction.** Move QtTune-specific bits (layer rules,
    domain prompts) behind config so other codebases can point the
    tribunal at themselves. More interesting if #5 lands.

Deliberately deferred: MAX_DEBATE_ROUNDS / loop-shape tuning — #2
supersedes; changing termination logic twice is wasted motion.

---

## Notes for Continuing Agents

- Models are assigned in the `MODELS` dict in config.py:
  reviewer = `laguna-xs-2.1` (33B MoE, num_ctx 16384 — smaller contexts
  truncate due to thinking tokens), engineer = `gemma4:12b`. Swap freely;
  that's the point of the dict.
- Temperature: 0.7 first round (exploration), 0.05 retries and later
  rounds (consistency). Retries on JSON decode errors append corrective
  user messages, not restarts.
- The feedback loop now functions (transcript re-rendered per round).
  Rounds 2+ respond to prior critique; convergence may happen before
  MAX_ROUNDS for the first time. Do not attribute convergence changes
  to temperature or guardrails; the loop itself changed the game.
- Decision records include `hedge_demotions` counts per round — when
  judging whether a verdict change came from the guardrail vs. prompt
  luck, read those counters. Note: in the 2026-10-09 re-measurement, 0
  demotions fired across all rounds while hedged blockers disappeared —
  the layer/context metadata changed phrasing at the source, upstream
  of the regex. Guardrails fixed the classes; context fixed the rhetoric.
- The judge derives "conditional" whenever questions/concerns exist,
  so demotions shift verdicts toward APPROVED_WITH_OPEN_QUESTIONS.
- The reviewer expects JSON-mode output (Ollama `format: "json"`).
  If a new model emits prose, parse failures fail closed to reject —
  check probe logs before assuming the model is bad at reviewing.
- Golden test fixture texts for hedge units are drawn verbatim from
  production decision records (see run_hedge_unit_tests docstring).
  Preserve production-derived provenance when extending.
- To modify judging or guardrail behavior: adjudication.py. To change
  what agents are asked: reviewer_prompt.py (+ bump PROMPT_VERSION).
  To change the debate protocol itself: debate.py. To swap models or
  knobs: config.py.
