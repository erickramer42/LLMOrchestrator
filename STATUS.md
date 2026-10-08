# STATUS — Project Map & Continuation Notes

Last updated: 2026-10-08 (module split; post "false-positive reduction v1")

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
- Two archived decision records: header review (core.h) and diff review
  (bridge refactor — the 1/12 precision datapoint)
- Module split (2026-10-08): single-file orchestrator decomposed into
  config / agent_client / adjudication / debate / golden_tests, with
  orchestrator.py reduced to a thin CLI entrypoint

**Known limitations (by design or pending):**
- Unresolved concerns/questions force MAX_ROUNDS_EXCEEDED → manual
  review. Intentional (fail-closed), but a granularity rework is queued.
- Multi-file diffs only inject the FIRST file's layer. Single-area diffs
  are fine; mixed core/bridge diffs get uniform treatment. Queued.
- Hedge demotion catches phrased speculation only. Confident-but-
  uninformed assertions pass through. Fix is definition-context
  injection (remediation #3), not a wider regex.
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
| `debate.py` | The debate loop: transcript construction, layer-note injection, guardrail application, rule-based judge, feedback composition, decision-record persistence (`_save_decision_record`). |
| `golden_tests.py` | Golden suite: 3 LLM-backed model fixtures + `run_hedge_unit_tests()` (7 deterministic guardrail regression cases, production-derived texts). |
| `reviewer_prompt.py` | Single source of truth for all prompts. PROMPT_VERSION stamped into decision records. REVIEWER_SYSTEM + IMPL_SCOPE_CLAUSE / HEADER_SCOPE_CLAUSE compose the two reviewer prompts. |
| `file_metadata.py` | File-path → layer mapping (core/bridge/app). `get_layer_constraints()` returns the injected transcript text telling the reviewer which rules apply. |
| `eval_harness/probe.py` | FP-rate probe: N runs against a clean fixture, aggregates blocker/verdict distribution, timeouts, parse failures. |
| `eval_harness/bakeoff.py` | Side-by-side model comparison on bug fixtures + clean fixture. |
| `eval_harness/__init__.py` | Package marker. |
| `docs/decisions/0001-model-selection.md` | ADR: model selection rationale, bake-off numbers, production precision analysis, remediation log. THE document for "why these models / why these guardrails." |
| `docs/portability_guide.md` | Running on other machines / codebases. |
| `docs/fixtures/qttune_bridge_refactor.diff` | Input diff for the archived bridge-refactor debate. Decision records are only interpretable against their input — keep pairs together. |
| `coach_artifacts/decision_debate_*.json` | Decision records: round history, hedge_demotions counts per round, verdict, metadata (prompt version, models). Intended consumer: "coach agent" for human-facing synthesis. |
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
6. **Quantify, then fix, then re-measure.** The ADR's pattern: measure
   FP rate → root-cause classes → remediate → re-measure. Continue it.
7. **Respect the module boundaries.** Network calls only in
   agent_client.py; adjudication stays pure (no I/O) so it remains
   CI-testable. Don't let conveniences erode that.

---

## Queued Work (priority order)

1. **Re-measure precision post-remediation.** Rerun the bridge-refactor
   diff debate; compare blocker precision to the 1/12 baseline. This is
   the validation of "false-positive reduction v1" and the ADR's table
   needs the new number. Use the SAME diff (docs/fixtures/) so it's
   comparable.
2. **Definition-context injection (remediation #3).** When a diff or
   snippet references structs/types (qttune_frame_t, etc.), locate and
   inject their definitions from QtTune headers into the transcript.
   Closes the "confident guessing" class the regex can't touch.
   Suggested approach: map type names → header paths, extract the
   typedef block, append as "TYPE DEFINITIONS (ground truth)".
3. **Judge granularity rework.** Split severity axis from resolution
   axis: APPROVED / APPROVED_WITH_FOLLOWUPS / BLOCKED, with open items
   recorded as severity-tagged follow-ups in the decision record instead
   of forcing MAX_ROUNDS_EXCEEDED. Design first; current behavior is
   defensible and documented. GitHub issue holds the notes.
4. **GitHub Actions CI.** The module split makes this easy: compile
   checks + hedge unit tests + judge logic tests, importing
   adjudication/golden_tests directly with no Ollama needed. Optionally
   mock or skip-if-unreachable for the LLM fixtures.
5. **Multi-file diff layer handling.** Parse ALL `+++ b/` headers in a
   diff (debate.extract_file_path currently returns only the first);
   inject a layer map keyed by file rather than a single layer.
6. **Retire the orchestrator re-export shim.** Once eval_harness/probe.py
   and bakeoff.py import from agent_client/config directly, delete the
   re-export block in orchestrator.py.
7. **Cross-link from QtTune repo README** to this tribunal.

---

## Notes for Continuing Agents

- Models are assigned in the `MODELS` dict in config.py:
  reviewer = `laguna-xs-2.1` (33B MoE, num_ctx 16384 — smaller contexts
  truncate due to thinking tokens), engineer = `gemma4:12b`. Swap freely;
  that's the point of the dict.
- Temperature: 0.7 first round (exploration), 0.05 retries and later
  rounds (consistency). Retries on JSON decode errors append corrective
  user messages, not restarts.
- Decision records include `hedge_demotions` counts per round — when
  judging whether a verdict change came from the guardrail vs. prompt
  luck, read those counters.
- The judge derives "conditional" whenever questions/concerns exist,
  so demotions shift verdicts toward APPROVED_WITH_OPEN_QUESTIONS.
  Expect faster convergence than the archived MAX_ROUNDS_EXCEEDED
  debates. That's intended.
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
  