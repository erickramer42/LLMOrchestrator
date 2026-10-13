# STATUS — Project Map & Continuation Notes

Last updated: 2026-10-13 (context pack phase 2: LLM purpose summaries,
24/24 fill; --index CLI wiring landed)

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
- Deterministic regression suite: 34 stdlib unittest cases in `tests/`,
  with Ollama faked at the HTTP layer. No model needed; CI-ready.
- FP-rate probe (5-run aggregates), model bake-off
- Repo indexer (`--index`): typedefs, constants and a layer map for QtTune
  (36 files, 7 types, 11 constants in the committed `repo_context.json`).
  Built, but not yet read by debates. Rebuilt 2026-10-13 with LLM purpose 
  summaries (24/24 source files, gemma4:12b); index records summary model and 
  SUMMARY_PROMPT_VERSION.
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
  Caveat (2026-10-10): that record is stamped `v3-engineer-added`, so
  any grouping by prompt_version files it with pre-fix runs. Its
  engineer round-2 blockers also restate the reviewer's round-1
  blockers nearly verbatim, including the m_currentFrameCount race that
  ADR-0002 classifies as confident-but-wrong. It shows feedback reaching
  the engineer, not independent corroboration.
- **Robustness and eval-integrity fixes (2026-10-10).** All pinned by
  `tests/`. Prompt templates are unchanged (rendered transcripts verified
  byte-identical on sample inputs), so PROMPT_VERSION stays v4. One
  input-dependent difference: a context whose path sits in a `//` comment
  now gets the correct layer note. QtTune header reviews get `core` where
  194320 ran as `unknown`; the new record field `inputs.layer` shows which.
  - Agent replies are schema-validated. Previously a reply with wrong
    keys was judged APPROVED_FOR_MERGE, and object-valued items, null
    arrays or non-object replies crashed the debate without a record.
  - Exhausted agent calls end the debate as AGENT_FAILURE with a reason,
    instead of looking like MAX_ROUNDS_EXCEEDED.
  - Layer detection: `// core/...` comment paths were classified
    `unknown`, and `// core/src/*bridge*` as bridge, which told the
    reviewer Qt is allowed in core. QML under app/qml/ now gets the app
    layer.
  - Eval scoring: probe printed CLEAN when every run failed to parse,
    and its timeout counter could never be non-zero. Bake-off dropped
    parse-failed bug cases from the detection denominator. The golden
    clean fixture passed on a parse failure. ADR-0001's "Timeouts 0/5"
    could not have read otherwise.
  - Decision records add original proposal, input hashes, layer,
    sampling settings and a `prompt_fingerprint`. Debate IDs get a
    random suffix.
  - Indexer: harvests every struct member (it used to skip every other
    one, dropping `qttune_frame_t.data[64]`), opaque/callback typedefs
    with doc comments, enum values, #define/hex constants, and no
    locals. LLM failures no longer cache the literal "PARSE_FAILURE" as a
    purpose; the cache is keyed by model and summary-prompt version.
  - CLI: modes are mutually exclusive, and inputs are read as UTF-8.

**Known limitations (by design or pending):**
- **Debates practically never converge.** Convergence needs the engineer
  to return zero blockers, concerns AND questions, and its prompt routes
  sequencing issues into concerns. Every archived debate ended at
  MAX_ROUNDS_EXCEEDED. An uncommitted 2026-10-10 smoke debate on QtTune's
  core.h showed the reviewer fully clean in round 1 and still not
  converging. Fail-closed is intentional; the convergence rule is backlog #2.
- **Feedback anchors rather than tests.** Critiques are appended inside
  the PROPOSAL section, so they read as author text, and the code never
  changes between rounds. In the 2026-10-10 smoke debate, the reviewer's
  open questions grew 0 → 4 → 9 across rounds as engineer concerns were
  fed back. Reviewer questions and engineer blockers are never fed back.
  See backlog #11.
- **Confident-but-wrong assertions are now the dominant FP class**
  (4/6 blockers in the re-measurement: thread-safety claims on
  GUI-thread-only state). Hedge regex provably cannot touch these —
  the fix is ground-truth context (repo context pack, backlog #1).
- **Hedge demotion is all-or-nothing.** One hedge word anywhere demotes
  the whole blocker, including confident, line-cited claims such as
  "memcpy at line 4 ... could overflow". See backlog #12.
- Diff-only review caps recall: both real bugs found by full-repo
  triage (drop-count starvation, staging-buffer last-write-wins) were
  invisible in the diff itself. Also addressed by the context pack.
- Reviewed code goes into the prompt unfenced (prompt-injection surface),
  context is cut at 8000 chars with no marker, and prompt token counts
  are not recorded, so silent prompt truncation is undetectable.
- Multi-file diffs only inject the FIRST file's layer. Queued.
- Golden model fixtures are nondeterministic, and they call the reviewer
  with bare snippets, bypassing the debate transcript builder (no layer
  note). Use `tests/` for pass/fail signals.
- Probe and bake-off measure the raw model through their own `call()`:
  no schema validation, no hedge demotion, no `config.py` settings. The
  probe always uses the header-scoped prompt.
- Evidence-pair gap: the header-review record (194320) and both probe
  logs used QtTune's core.h, which is not in `docs/fixtures/`.

---

## File Map

| Path | Purpose |
|---|---|
| `orchestrator.py` | Thin CLI entrypoint: argument parsing and dispatch only. Modes `--golden`, `--proposal` and `--index` are mutually exclusive; inputs read as UTF-8. Re-exports key symbols (call_agent, MODELS, derive_verdict, demote_hedged_blockers) as a transition shim for older importers. |
| `config.py` | Central configuration: MODELS dict, num_ctx, timeouts, temperatures, and prompt composition (REVIEWER_IMPL_PROMPT / REVIEWER_HEADER_PROMPT). Single place to swap models. |
| `agent_client.py` | Ollama client. Single agent turn, JSON-mode enforcement, retries with corrective messages for invalid JSON and for replies rejected by an optional `validate` callback. `failure_result(reason)` returns a fresh fail-closed sentinel with `failure_reason`. The ONLY module that touches the network. |
| `adjudication.py` | Pure adjudication logic, no I/O: `normalize_agent_output()` (per-role schema validation and coercion), `derive_verdict()` (content-based verdicts; anything malformed → reject) and `demote_hedged_blockers()` (hedge regex guardrail). CI-importable with no model serving. |
| `debate.py` | The debate loop. Model-facing text lives in `STATIC_TEMPLATE`, `TRANSCRIPT_TEMPLATE` and `FEEDBACK_TEMPLATE` (prompts: edits bump PROMPT_VERSION). Re-renders the transcript every round (fixed 2026-10-09, see ADR-0002 erratum). Ends with AGENT_FAILURE on an exhausted agent call. Writes decision records with provenance. |
| `golden_tests.py` | Golden suite: 3 LLM-backed model fixtures (an agent failure fails the fixture) + `run_hedge_unit_tests()` (7 deterministic guardrail regression cases, production-derived texts). |
| `reviewer_prompt.py` | Single source of truth for agent system prompts. PROMPT_VERSION stamped into decision records. REVIEWER_SYSTEM + IMPL_SCOPE_CLAUSE / HEADER_SCOPE_CLAUSE compose the two reviewer prompts. Also holds FAILURE_SENTINEL. |
| `file_metadata.py` | File-path → layer mapping. Order: core first, then UI dirs and `.qml` → app, then `app/` or "bridge" → bridge. `get_layer_constraints()` returns the injected transcript text telling the reviewer which rules apply. |
| `repo_context.py` | Offline indexer for the repo context pack (`orchestrator.py --index ../qttune [--no-llm]`). Typedefs by kind (struct, union, enum, opaque, function_pointer) with members, enum values and doc comments; `#define` and const/constexpr numeric constants; layer map; optional LLM purpose lines cached by content hash, model and `SUMMARY_PROMPT_VERSION`. Committed context pack for QtTune, rebuilt 2026-10-13 with LLM purpose summaries (24/24, gemma4:12b). Not yet read by debate.py. |
| `repo_context.json` | Committed context pack for QtTune (deterministic `--no-llm` build, regenerated 2026-10-10). Not yet read by debate.py. |
| `eval_harness/probe.py` | FP-rate probe: N runs against a clean fixture (`--fixture` required). `summarize()` classifies CLEAN / BORDERLINE / SYSTEMATIC / NO_DATA; parse failures and timeouts count against the model. |
| `eval_harness/bakeoff.py` | Side-by-side model comparison on bug fixtures + clean fixture. `tally()` keeps tp + fn == bug cases; a failed bug case is a miss. |
| `eval_harness/__init__.py` | Package marker. |
| `tests/test_deterministic.py` | Stdlib unittest regression suite (`python -m unittest discover -s tests -v`). Fake Ollama HTTP layer, so the real client/judge/debate paths run with no model. Includes the 7 hedge units and CLI checks. CI-ready. |
| `docs/decisions/0001-model-selection.md` | ADR-0001: model selection rationale, bake-off numbers, eval harness bug history. THE document for "why these models on this hardware." Its timeout row predates a working timeout counter. |
| `docs/decisions/0002-adjudication-and-fp-remediation.md` | ADR-0002: the false-positive arc — 1/12 baseline triage, guardrail design, 1/6 re-measurement, residual class analysis, erratum. THE document for "why these guardrails." |
| `docs/portability_guide.md` | Running on other machines / codebases. Predates the module split (MODELS is in config.py; keys are code_reviewer / auto_engineer). |
| `docs/fixtures/qttune_bridge_refactor.diff` | Input diff for the bridge-refactor debates (baseline AND v1 re-measurement — same fixture enables comparability). Keep record/fixture pairs together. |
| `coach_artifacts/decision_debate_*.json` | Decision records: round history, hedge_demotions counts per round, verdict, metadata (prompt version, models). Four archived: header review (194320), baseline diff review (203917), v1 re-measurement (014257), feedback-loop smoke debate (153541, see caveat above). Records written from 2026-10-10 also carry `prompt_fingerprint`, sampling settings, input hashes, original proposal, layer and `agent_failures`. Intended consumer: "coach agent" for human-facing synthesis. |
| `probe_logs/fp_*.json` | 5-run probe aggregates backing the FP-rate claims in the ADR. |
| `requirements.txt` | Runtime deps (requests only, as of this writing). |
| `.gitignore` | `gold_tests/run_*.json` outputs are transient and NOT committed; neither is `repo_context_cache.json`. Eval evidence lives in probe_logs/ and coach_artifacts/. |

**Module dependency direction (acyclic):** reviewer_prompt + file_metadata
(leaves) → config → agent_client and adjudication (parallel layers; callers
pass adjudication validators into agent_client as callbacks, so neither
imports the other) → debate + golden_tests + repo_context →
orchestrator (CLI handle; imports repo_context lazily for `--index`).
`tests/` sits on top of everything.

---

## Conventions (do not silently violate)

1. **Derived verdicts only.** Never trust a model's self-reported
   verdict label. Judge reads blockers/questions/concerns arrays
   (adjudication.derive_verdict).
2. **Fail closed.** Parse failure, schema violation, timeout, empty input
   → reject / manual review (`AGENT_FAILURE - MANUAL_REVIEW_REQUIRED`).
   Never default to approve; a missing array is never "no problems".
   (Enforced in agent_client.call_agent + adjudication.)
3. **Blockers must be demonstrable.** Speculation belongs in questions.
   If you widen HEDGE_PATTERNS in adjudication.py, the 7 unit cases in
   `run_hedge_unit_tests()` (golden_tests.py) must still pass — several
   are negative controls that assert confident statements are NOT demoted.
4. **Prompts are versioned.** Any prompt change bumps PROMPT_VERSION in
   reviewer_prompt.py so eval results correlate to prompt revisions.
   The transcript templates in debate.py and the layer notes in
   file_metadata.py are prompts too. Records also carry a
   `prompt_fingerprint` of the exact templates used. The indexer's
   SUMMARY_PROMPT has its own SUMMARY_PROMPT_VERSION.
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

Suggested order as of 2026-10-10: #3 CI → #13 evidence trail → #2 judge
+ #11 transcript v5 → #1 retrieval and third re-measurement → the rest.

1. **Repo context pack** (subsumes definition-context injection; now the
   top priority since re-measurement confirmed confident-but-wrong as
   the dominant residual class). **Indexer done** (repo_context.py,
   harvesting fixed and verified 2026-10-10). Remaining: debate-time
   retrieval keyed on diff references; optional --repo-scan holistic
   mode. Gap: the predicted collapse of the 4 thread-safety FPs needs
   queued-connection call sites (`connect(..., Qt::QueuedConnection)`),
   which the indexer does not harvest yet. Ground truth for eval: 4
   production findings from manual repo scan (coolant overflow, CI test
   gap, stale page number, doc test counts), 2026-10-08. When built:
   re-measure the bridge diff a third time. Score round-1 output, or do
   #2 and #11 first, because the current feedback design contaminates
   rounds 2–3.
2. **Judge granularity rework.** Split severity from resolution:
   APPROVED / APPROVED_WITH_FOLLOWUPS / BLOCKED with severity-tagged
   follow-ups recorded in the decision record. Design first; current
   fail-closed behavior is defensible. Minimal option: converge as
   APPROVED_WITH_OPEN_QUESTIONS when neither agent has blockers (a
   verdict the judge already has). Evidence: every debate so far ended
   at max rounds.
3. **GitHub Actions CI.** Now just two commands, no Ollama:
   `python -m py_compile *.py eval_harness/*.py tests/*.py` and
   `python -m unittest discover -s tests -v`.
4. **Per-debate cost/latency telemetry.** Wall-clock per round, plus
   Ollama's eval_count, prompt_eval_count and done_reason stamped into
   decision records. prompt_eval_count near NUM_CTX reveals silent
   prompt truncation.
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
   imports from agent_client/config directly (unifies the harness's
   private `call()` functions with the production client).
10. **Codebase abstraction.** Move QtTune-specific bits (layer rules,
    domain prompts) behind config so other codebases can point the
    tribunal at themselves. More interesting if #5 lands.
11. **Transcript protocol v5** (one versioned prompt change, predicted
    and measured as a unit): move prior critique out of the PROPOSAL
    section into its own section marked unverified; ask each agent to
    uphold or withdraw each prior item with a citation; feed back
    reviewer questions and engineer blockers too; fence diff and context
    as untrusted data; add a truncation marker. Bump PROMPT_VERSION.
12. **Hedge gate decision.** Demote only hedged blockers that cite no
    line (`line N` or `file.ext:N`). Checked 2026-10-10: passes all 7
    hedge units, but a hedged, line-cited claim would stay a blocker.
    Needs production-derived controls first. Low urgency: the guardrail
    fired 0 times in the last re-measurement.
13. **Evidence-trail repair.** Commit QtTune's core.h under
    docs/fixtures (pairs for 194320 and both probe logs); rerun the
    probe with the fixed scoring; correct ADR-0001's timeout row; add
    the 153541 version-stamp caveat to the ADR-0002 erratum.
14. **Client hardening.** Pass the JSON schema as Ollama's `format`
    (structured outputs) instead of `"json"`; route golden fixtures
    through the debate transcript builder so layer detection is
    exercised; add an implementation-prompt option to the probe.

Deliberately deferred: MAX_DEBATE_ROUNDS / loop-shape tuning — #2
supersedes; changing termination logic twice is wasted motion.

---

## Notes for Continuing Agents

- Models are assigned in the `MODELS` dict in config.py:
  reviewer = `laguna-xs-2.1` (33B MoE, num_ctx 16384 — smaller contexts
  truncate due to thinking tokens), engineer = `gemma4:12b`. Swap freely;
  that's the point of the dict.
- Temperature: 0.7 first round (exploration), 0.05 retries and later
  rounds (consistency). Retries on invalid JSON or schema violations
  append corrective user messages, not restarts.
- The feedback loop functions (transcript re-rendered per round), but
  debates still end at MAX_ROUNDS because the engineer must be fully
  clean to converge (see Known limitations). Do not attribute
  convergence changes to temperature or guardrails; the loop and the
  termination rule drive it.
- Decision records include `hedge_demotions` counts per round — when
  judging whether a verdict change came from the guardrail vs. prompt
  luck, read those counters. Note: in the 2026-10-09 re-measurement, 0
  demotions fired across all rounds while hedged blockers disappeared —
  the layer/context metadata changed phrasing at the source, upstream
  of the regex. Guardrails fixed the classes; context fixed the rhetoric.
- When grouping runs, compare `prompt_fingerprint` (records from
  2026-10-10 on), not only PROMPT_VERSION; read `inputs.layer` too.
- The judge derives "conditional" whenever questions/concerns exist,
  so demotions shift verdicts toward APPROVED_WITH_OPEN_QUESTIONS.
- The reviewer expects JSON-mode output (Ollama `format: "json"`).
  If a new model emits prose or the wrong keys, the debate ends as
  AGENT_FAILURE; read `outputs.agent_failures` in the record. A reason
  mentioning `done_reason=length` means output was truncated: raise
  NUM_CTX. Check probe logs before assuming the model is bad at reviewing.
- Run ad-hoc debates from a scratch directory: `coach_artifacts/` is
  CWD-relative, and records without a committed fixture shouldn't be
  committed.
- Golden test fixture texts for hedge units are drawn verbatim from
  production decision records (see run_hedge_unit_tests docstring).
  Preserve production-derived provenance when extending.
- Pin every fix with a case in `tests/test_deterministic.py`; its
  `fake_ollama()` helper drives the real client and debate code.
- To modify judging or guardrail behavior: adjudication.py. To change
  what agents are asked: reviewer_prompt.py or the templates in debate.py
  (+ bump PROMPT_VERSION). To change the debate protocol itself:
  debate.py. To swap models or knobs: config.py.
