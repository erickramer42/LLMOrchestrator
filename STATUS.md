# STATUS — Project Map & Continuation Notes

Last updated: 2026-10-13 (context-pack phase 3: retrieval wired into
debates, queued-connection call-site harvester, N=3 measurement
recorded in ADR-0002)

Purpose of this file: anyone picking up this repo can
orient in five minutes, run the existing validation, and continue the
queued work without reverse-engineering the ADRs.

---

## Current State

**Working and validated:**
- Adversarial debate loop, up to 3 rounds, with a rule-based judge
- Derived verdicts (content-based, not model self-report)
- Schema validation of every agent reply before judging
  (`adjudication.normalize_agent_output`). Bad replies are retried with a
  corrective message (temp fallback 0.05), then fail closed: the debate
  ends as `AGENT_FAILURE - MANUAL_REVIEW_REQUIRED` with a recorded
  `failure_reason`.
- Layer metadata injection (core / bridge / app)
- Hedge-language demotion guardrail (deterministic, regression-tested)
- Golden suite: 3 model fixtures + 7 deterministic guardrail units = 10/10
  (re-run live 2026-10-10 after the fixes below)
- Deterministic regression suite: 44 stdlib unittest cases in `tests/`,
  with Ollama faked at the HTTP layer. No model needed; CI-ready.
- FP-rate probe (5-run aggregates), model bake-off
- Repo indexer (`--index`): typedefs, constants, layer map, LLM purpose
  summaries and queued-connection call sites for QtTune (rebuilt
  2026-10-13: 40 files, 28/28 source purposes, 2 call sites).
- **Repo-context retrieval, measured (2026-10-13, v5-context-pack):**
  `build_context_pack()` in repo_context.py retrieves purposes, types,
  constants and queued-connection call sites tied to the diff;
  debate.py injects them into the transcript under a 6000-char budget
  (non-fatal on failure, recorded via `repo_context_pack` in decision
  records; pack text included in the prompt fingerprint). N=3
  measurement on the bridge-refactor fixture: thread-safety FP class
  eliminated in 3/3 runs; round-1 precision 2/10 (was 1/6). Both TPs
  are real previously-shipped bugs (see ADR-0002, fourth measurement,
  including the retroactive re-adjudication flag on the v1 triage).
- Module split (2026-10-08): single-file orchestrator decomposed into
  config / agent_client / adjudication / debate / golden_tests, with
  orchestrator.py reduced to a thin CLI entrypoint
- **False-positive reduction v1, measured twice:** baseline 1/12 blocker
  precision (2026-10-07, decision_debate_20261007_203917) → 1/6 after
  layer metadata + hedge demotion (2026-10-09,
  decision_debate_20261009_014257, same diff). Layer-class blockers:
  7 → 0. Full analysis in ADR-0002. NOTE: the "confident-but-wrong"
  class counts in both runs are flagged for re-triage — see ADR-0002
  re-adjudication flag.
- **Feedback loop repair (2026-10-09):** transcript re-rendered per round
  so `REVISE ADDRESSING` feedback reaches agents; archived records read
  as multi-sample measurements; prompt version bumped to v4. Caveat
  (2026-10-10): the 153541 smoke record is stamped `v3-engineer-added`;
  see ADR-0002 erratum.
- **Robustness and eval-integrity fixes (2026-10-10).** All pinned by
  `tests/`. See ADR-0002 and the 2026-10-10 STATUS history: schema
  validation, fail-closed agent exhaustion, layer detection fixes, eval
  scoring fixes, decision-record provenance, indexer harvest fixes,
  UTF-8 input reads.
- GitHub Actions CI (2026-10-13): compile checks + deterministic
  regression suite, no Ollama needed.

**Known limitations (by design or pending):**
- **Deletion-hallucination is now the dominant FP class** (8 total
  across the N=3 context-pack runs, 6/0/1 by run): the reviewer
  fabricates surviving references to code removed together in the diff.
  Candidate fix: ground removed symbols from the diff's minus side
  (backlog #15).
- **Hedge demotion can demote true claims.** It fired once in the N=3
  measurement, on a hedged formulation of a genuine thread-safety
  finding. "Hedged" does not imply "wrong" (backlog #12).
- **num_ctx crowding in rounds 2+:** the context pack (~2k chars) plus
  feedback growth occasionally exhausts 16384 ctx
  (`done_reason=length`, one AGENT_FAILURE in the N=3). The retrieval
  budget competes with the debate loop's growth (backlogs #4/#16).
- **Debates practically never converge.** Convergence needs the engineer
  to return zero blockers, concerns AND questions. Every archived debate
  ended at MAX_ROUNDS_EXCEEDED. Fail-closed is intentional; the
  convergence rule is backlog #2.
- **Feedback anchors rather than tests,** and the live loop can undo
  retrieval's gains: in the pilot, engineer concerns reintroduced
  thread-safety blockers in round 3 after a clean round 1. Additional
  reason to score round-1 output (see backlog #11).
- Diff-only review caps recall. Partially mitigated by the context pack;
  the pack only carries what the indexer harvests.
- Reviewed code goes into the prompt unfenced (prompt-injection surface),
  and prompt token counts are not recorded, so silent prompt truncation
  is undetectable (backlog #4).
- Multi-file diffs only inject the FIRST file's layer. Queued (#8).
- Golden model fixtures are nondeterministic and bypass the debate
  transcript builder. Use `tests/` for pass/fail signals.
- Probe and bake-off measure the raw model through their own `call()`:
  no schema validation, no hedge demotion, no `config.py` settings.
- Evidence-pair gap: the header-review record (194320) and both probe
  logs used QtTune's core.h, which is not in `docs/fixtures/` (#13).
- **Historical FP labels suspect:** the v1 re-measurement's
  "confident-but-wrong" thread-safety FPs were refuted using maintained
  QtTune, but the fixture post-state genuinely races — re-triage
  pending (ADR-0002 re-adjudication flag, backlog #17).

---

## File Map

| Path | Purpose |
|---|---|
| `orchestrator.py` | Thin CLI entrypoint: argument parsing and dispatch only. Modes `--golden`, `--proposal` and `--index` are mutually exclusive; inputs read as UTF-8. Re-exports key symbols as a transition shim. |
| `config.py` | Central configuration: MODELS dict, num_ctx, timeouts, temperatures, and prompt composition. Single place to swap models. |
| `agent_client.py` | Ollama client. Single agent turn, JSON-mode enforcement, retries with corrective messages. The ONLY module that touches the network. |
| `adjudication.py` | Pure adjudication logic, no I/O: `normalize_agent_output()`, `derive_verdict()`, `demote_hedged_blockers()`. CI-importable. |
| `debate.py` | The debate loop. Transcript templates incl. `REPO_CONTEXT_TEMPLATE`; loads `repo_context.json`, calls `build_context_pack`, injects retrieval into the transcript, records `repo_context_pack` diagnostics in decision records. Ends with AGENT_FAILURE on exhausted agent calls. |
| `golden_tests.py` | Golden suite: 3 LLM-backed model fixtures + `run_hedge_unit_tests()` (7 deterministic guardrail cases, production-derived texts). |
| `reviewer_prompt.py` | Single source of truth for agent system prompts. PROMPT_VERSION (currently v5-context-pack). Also holds FAILURE_SENTINEL. |
| `file_metadata.py` | File-path → layer mapping and layer constraint notes. |
| `repo_context.py` | Offline indexer (`orchestrator.py --index ../qttune [--no-llm]`) AND debate-time retrieval (`harvest_callsites`, `build_context_pack`): modified-file purposes, referenced types/constants, queued-connection call sites with paren-depth statement scanning, budget-enforced truncation. Consumed by debate.py since v5-context-pack. |
| `repo_context.json` | Committed context pack for QtTune (40 files, 28 LLM purposes, 2 queued-connection call sites; repo_root field removed 2026-10-13 — local-path leak). Read by debate.py at runtime. |
| `eval_harness/probe.py` | FP-rate probe: N runs against a clean fixture. CLEAN / BORDERLINE / SYSTEMATIC / NO_DATA. |
| `eval_harness/bakeoff.py` | Side-by-side model comparison on bug + clean fixtures. |
| `eval_harness/__init__.py` | Package marker. |
| `tests/test_deterministic.py` | Stdlib unittest regression suite, incl. retrieval/callsite-harvesting cases. Fake Ollama HTTP layer. CI-ready. |
| `tests/test_retrieval.py` | Retrieval unit tests: paren-depth scanning, multiline lambda connects, truncation-budget accounting. |
| `docs/decisions/0001-model-selection.md` | ADR-0001: model selection rationale, bake-off numbers. |
| `docs/decisions/0002-adjudication-and-fp-remediation.md` | ADR-0002: the false-positive arc — baseline triage, v1 guardrails, re-measurement, live-loop control, context-pack N=3 results with retroactive re-adjudication flag. |
| `docs/portability_guide.md` | Running on other machines / codebases. Predates the module split. |
| `docs/fixtures/qttune_bridge_refactor.diff` | Input diff for all bridge-refactor debates. Provenance (established 2026-10-13): reverse patch of QtTune `e0c4c31`; post-state identical to committed `8ffbf19` (blob `1c195f8`). |
| `coach_artifacts/decision_debate_*.json` | Decision records. Nine archived: header review (194320), baseline (203917), v1 re-measurement (014257), feedback smoke (153541, see erratum caveat), live-loop control (170208), context-pack pilot (201540, unscored), and three scored context-pack runs (203802, 204845, 210548). Records from 2026-10-10 on carry `prompt_fingerprint`, sampling settings, input hashes, layer, `agent_failures`; v5 records carry `repo_context_pack`. |
| `probe_logs/fp_*.json` | 5-run probe aggregates backing the FP-rate claims. |
| `requirements.txt` | Runtime deps (requests). |
| `.github/workflows/` | CI: compile checks + regression suite, no Ollama. |
| `.gitignore` | Transient outputs (gold_tests/run_*.json, repo_context_cache.json, *.bat) not committed. |

**Module dependency direction (acyclic):** reviewer_prompt + file_metadata
(leaves) → config → agent_client and adjudication (parallel layers) →
debate + golden_tests + repo_context → orchestrator. `tests/` sits on
top of everything.

---

## Conventions (do not silently violate)

1. **Derived verdicts only.** Never trust a model's self-reported
   verdict label. Judge reads blockers/questions/concerns arrays.
2. **Fail closed.** Parse failure, schema violation, timeout, empty
   input → reject / manual review. Never default to approve.
3. **Blockers must be demonstrable.** Speculation belongs in questions.
   HEDGE_PATTERNS changes must keep the 7 hedge units passing.
4. **Prompts are versioned.** Any change to what agents see bumps
   PROMPT_VERSION (transcript templates and retrieval text are prompts
   too; pack text is in the fingerprint). Currently v5-context-pack.
5. **Evidence pairs.** Every committed decision record needs its input
   fixture committed alongside (docs/fixtures/).
6. **Predict before measuring.** Expected outcome written to the ADR
   before any eval run; results recorded next to it. Practiced for v1,
   the control run, and the N=3 context-pack measurement.
7. **Quantify, then fix per class, then re-measure.** Attribute per
   failure class; publish misses and corrections, not just wins.
8. **Respect the module boundaries.** Network only in agent_client.py;
   adjudication stays pure. Retrieval reads files (repo_context.py),
   never the network.

---

## Backlog (ideas, loosely ordered)

Suggested order as of 2026-10-13: #15 deletion-hallucination →
#12 hedge gate → #4/#16 context budget + telemetry → #2 judge +
#11 transcript v6 → #17 re-triage → the rest.

1. **Repo context pack — DONE (2026-10-13).** Indexer, callsite
   harvester, debate-time retrieval and the third measurement are all
   landed (ADR-0002, fourth measurement). Kept for history; open
   follow-ups became #15–#17 below.
2. **Judge granularity rework.** Split severity from resolution;
   minimal option: converge as APPROVED_WITH_OPEN_QUESTIONS when
   neither agent has blockers.
3. **GitHub Actions CI — DONE (2026-10-13).**
4. **Per-debate cost/latency telemetry.** Wall-clock per round, plus
   eval_count, prompt_eval_count and done_reason stamped into records.
   prompt_eval_count near NUM_CTX reveals silent truncation — directly
   relevant to #16.
5. **Cloud model support.** OpenAI-compatible endpoint in
   agent_client.py; golden suite first; segregated results.
6. **Chained/escalated debates.** On MAX_ROUNDS_EXCEEDED, re-submit
   unresolved questions as a fresh debate. Depends on #2.
7. **Stable real-diff corpus.** 3–5 triaged real diffs with known
   expected outcomes. The reverse-of-merged-commit technique that
   produced the current fixture is a repeatable way to build this.
8. **Multi-file diff layer handling.** Parse all `+++ b/` headers;
   inject a layer map keyed by file.
9. **Retire the orchestrator re-export shim.**
10. **Codebase abstraction.** Move QtTune-specific bits behind config.
11. **Transcript protocol v6** (one versioned prompt change, predicted
    and measured as a unit): move prior critique out of PROPOSAL into
    an unverified section; uphold-or-withdraw with citation; feed back
    reviewer questions and engineer blockers; fence untrusted diff/
    context; add truncation markers.
12. **Hedge gate decision.** Demote only hedged blockers that cite no
    line. NEW EVIDENCE (2026-10-13): the guardrail demoted a hedged
    TRUE claim in the N=3 run; treats this as urgent, not "low".
13. **Evidence-trail repair.** Commit QtTune's core.h under
    docs/fixtures; rerun the probe with fixed scoring; correct
    ADR-0001's timeout row.
14. **Client hardening.** Pass the JSON schema as Ollama's `format`
    (structured outputs); route golden fixtures through the transcript
    builder.
15. **Deletion-hallucination remediation (NEW, top priority).** Ground
    "removed symbols" from the diff's minus side: a blocker claiming a
    surviving reference to symbol X must verify X is not in the removed
    set. Deterministic pre-judge check in adjudication.py, or retrieval
    that lists removed symbols alongside survivors. Predict + measure
    per convention 7 — this is the new dominant FP class (8 in N=3).
16. **Context budget negotiation (NEW).** num_ctx crowding: drop the
    pack from rounds 2+, trim feedback accumulation, or raise num_ctx
    within VRAM. Decide with #4 telemetry data.
17. **Historical re-triage (NEW).** Re-read the v1 (014257) and
    control (170208) thread-safety blockers against the fixture's
    actual post-state (which does read m_currentFrameCount on the
    worker thread); correct the FP/TP labels in ADR-0002 and the
    README precision table. The re-adjudication flag is already
    recorded; this executes it.

Deliberately deferred: MAX_DEBATE_ROUNDS / loop-shape tuning — #2
supersedes.

---

## Notes for Continuing Agents

- Models are assigned in the `MODELS` dict in config.py:
  reviewer = `laguna-xs-2.1` (num_ctx 16384), engineer = `gemma4:12b`.
- Temperature: 0.7 first round, 0.05 retries and later rounds.
- Round-1 output is the scored arm for measurements: the live feedback
  loop demonstrably carries engineer concerns back into reviewer
  blockers (pilot round 3, 2026-10-13), so rounds 2+ mix retrieval and
  anchoring effects.
- Decision records include `hedge_demotions` per round and (v5 on)
  `repo_context_pack` retrieval diagnostics. When grouping runs,
  compare `prompt_fingerprint`, not only PROMPT_VERSION.
- The judge derives "conditional" whenever questions/concerns exist.
- If an agent failure reason mentions `done_reason=length`, output was
  truncated: the pack + feedback may be crowding num_ctx (see #16)
  before assuming the model is bad.
- Run ad-hoc debates from a scratch directory: `coach_artifacts/` is
  CWD-relative.
- Pin every fix with a case in `tests/`; `fake_ollama()` drives the
  real client and debate code.
- To modify judging or guardrails: adjudication.py. To change what
  agents are asked: reviewer_prompt.py or the templates in debate.py
  (+ bump PROMPT_VERSION). Retrieval logic: repo_context.py. To swap
  models or knobs: config.py.
- Fixture provenance (2026-10-13, forensics): the bridge-refactor
  fixture is the reverse patch of QtTune commit `e0c4c31`; post-state
  byte-identical to committed `8ffbf19` (blob `1c195f8`, verified via
  `git log --all --find-object=1c195f8`). Both N=3 TPs are real
  previously-shipped bugs, later fixed in QtTune. Any future triage of
  this fixture must score against the diff's post-state, NOT current
  QtTune — that mistake is what #17 corrects.
