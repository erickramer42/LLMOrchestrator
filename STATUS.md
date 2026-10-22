# STATUS — Project Map & Backlog

Last updated: 2026-10-22 (record provenance and per-attempt telemetry;
context window raised to 24576 and output capped at 12288 from live
telemetry; v6 diff-authoritative retrieval with the index rebuilt from
the fixture's base; backlog #18–#21 filed; convergence rule j2, backlog
#2's minimal option; CI on Python 3.11 and 3.13; round-1 measurement
mode and scorer)

Purpose of this file: anyone picking up this repo can orient in five
minutes, run the existing validation, and continue the queued work
without reverse-engineering the ADRs.

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
- Deterministic regression suite: 100 stdlib unittest cases in `tests/`,
  with Ollama faked at the HTTP layer. No model needed; CI-ready.
- FP-rate probe (5-run aggregates), model bake-off
- Repo indexer (`--index`): typedefs, constants, layer map, LLM purpose
  summaries and queued-connection call sites for QtTune. The index
  records the commit it was built from. The committed index was rebuilt
  2026-10-22 from QtTune `e0c4c31`, the bridge fixture's base: 35 files,
  24/24 source purposes, 7 types, 10 constants, 1 call site. Earlier
  builds used `6b58c3a`, a later tree than the fixture.
- **Repo-context retrieval, measured (2026-10-13, v5-context-pack):**
  `build_context_pack()` in repo_context.py retrieves purposes, types,
  constants and queued-connection call sites tied to the diff;
  debate.py injects them into the transcript under a 6000-char budget
  (non-fatal on failure, recorded via `repo_context_pack` in decision
  records). N=3
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
  regression suite, no Ollama needed. Since 2026-10-22 it installs from
  `requirements.txt` and runs on Python 3.11 and 3.13.
- **Retrieval fixes (2026-10-21, PROMPT_VERSION v5.1-retrieval-fidelity).**
  Index and cache paths are module-relative, so retrieval works from any
  working directory; an unavailable index prints a warning and returns
  `retrieval_error`. Identifier matching is an exact intersection with indexed
  names (ALL_CAPS `#define`s were unreachable). The pack now shows comment-free
  typedef declarations with doc comments, call-site summaries that keep
  the connection type, word-boundary purpose clipping, and one line for
  build/docs files; nothing is injected when nothing matches. The index
  was rebuilt from QtTune `6b58c3a` (verified against all 28 cached
  digests; cached purposes reused, zero model calls). The fixture's pack
  grew from 2,023 to 2,816 chars. Precision not yet re-scored: the seven
  2026-10-22 telemetry runs below are unscored.
- **Provenance and telemetry (2026-10-22, PROMPT_VERSION
  v5.2-pack-sections; code review 2026-10-21 findings 5, 6, 8).**
  - Records keep the exact pack text, its SHA-256, the index version and
    `PACK_FORMAT_VERSION` under `repo_context_pack`.
  - `prompt_fingerprint` hashes templates only, plus
    `REPO_CONTEXT_TEMPLATE` and `PACK_FORMAT_VERSION` when a pack was
    used. Runs of one prompt on different diffs now share a fingerprint.
  - Each round records `telemetry`: one entry per agent attempt with
    `prompt_eval_count`, `eval_count`, thinking and reply sizes,
    `done_reason`, prompt chars, wall time and outcome (backlog #4).
    Failed attempts also keep the last 400 chars of thinking and reply,
    to tell a loop from long reasoning.
  - `build_context_pack` reports `used` as the real pack length and
    truncates on it. Empty section headers are gone. Related call sites
    no longer need a direct call site and are counted. A malformed index
    degrades the debate to no retrieval instead of crashing it.
  - The bridge fixture's pack is byte-identical to v5.1's.
- **Context window and output cap (2026-10-22, backlog #16; ADR-0002
  telemetry follow-ups).** Seven live telemetry runs on the bridge
  fixture showed a stable ~9.4K–10.2K-token prompt, while the output,
  thinking included, varies widely.
  - **`NUM_CTX` 16384 → 24576:** finished reviewer replies reach 10,097
    output tokens, which 16384 cannot hold.
  - **`NUM_PREDICT` 12288:** some attempts loop in their thinking and
    would fill any window. The cap stops them, and the retry recovers.
    Verified live (15cc3f, 5b3f1d): two runaways stopped at exactly
    12,288 tokens, and both retries recovered.
  - Debates only; probe and bake-off keep 16384, uncapped.
- **Diff-authoritative retrieval (2026-10-22, PROMPT_VERSION
  v6-diff-authoritative, pack format f3; code review 2026-10-21
  finding 1).**
  - The template calls the pack a snapshot of the indexed tree and the
    diff authoritative. "Ground truth" and "verified facts" are gone.
  - Constants, types and call sites from a modified file that use an
    identifier only the diff's removed lines contain are omitted and
    named under OMITTED. Purposes that mention one are annotated.
  - The index records `source_commit`/`source_dirty`; records carry
    `repo_context_pack.index_commit`.
  - Fixture pack (2,562 chars): `MaxInFlightFrames` and the
    `m_inFlightFrames` call site are omitted, and both `SignalListModel`
    purposes are annotated. Not yet measured live.
- **Convergence rule j2 (2026-10-22, backlog #2 minimal option).** A
  round converges once neither agent has a blocker: open questions and
  concerns give `APPROVED_WITH_OPEN_QUESTIONS` instead of another round.
  The rule is `adjudication.convergence_verdict`; records stamp
  `metadata.judge_version`. Replayed over the 16 archived records, it
  changes only header review 194320, which would converge in round 1.
  Round-1 measurements are unaffected (ADR-0002, convergence rule j2).
- **Round-1 measurement mode and scorer (2026-10-22).** Measurements
  score only the reviewer's round-1 first attempt, which never sees the
  engineer. In the seven v5.2 telemetry runs that call took 2.2 of a
  debate's 10.1 minutes on average.
  - `debate.run_round1_review` makes that one call and saves
    `coach_artifacts/measurement_*.json` (mode `round1_reviewer`,
    verdict `NOT_ADJUDICATED - ROUND1_MEASUREMENT`). It shares its setup
    with `run_debate`. A test pins that it sends the identical request
    as a debate's first call, and the records share the debate's
    `prompt_fingerprint`. No prompt changed, so PROMPT_VERSION stays v6.
  - `python -m eval_harness.round1 run` collects N samples.
  - `python -m eval_harness.round1 score` scores measurement and debate
    records. It keeps first attempts on the given diff, counts M1, and
    lists M2 candidates: blockers naming a removed identifier that the
    post-state lacks (`git grep -w`). Candidates still need confirming
    by hand.
  - Scorer check: on the v5.2 arm-1 records it reproduces the
    hand-scored M1 per run exactly (2, 1, 1, 0, 0, 0) and excludes
    3026b2 as a retry. The 10 M2 candidates include all 3 confirmed M2
    blockers; the other 7 object to removals.

**Known limitations (by design or pending):**
- **Deletion hallucination: the reviewer fabricates surviving
  references to code the diff removes.** It was the dominant FP class
  in the v5 N=3 (8 total, 6/0/1 by run). In six scorable v5.2 runs it
  fell to 3 (0.5 per run), every one citing a symbol the stale context
  pack asserts. One cites a line number that exists only in the indexed
  tree (ADR-0002, fifth measurement, arm 1). v6 fixes the retrieval
  side: the diff is authoritative and removed entries are omitted. The
  ablation was skipped, so whether the class needs the pack is
  unanswered; #15 (a pre-judge check) waits on the v6 baseline.
- **The bridge fixture's proposal contradicts its diff.** Every run
  since 2026-10-07 used *"Review: coalesced signal updates with
  LiveView Page v0.3.0 phase 2"*, the subject of `e0c4c31`, which adds
  the LiveView page. The fixture is its reverse and deletes it. Many
  round-1 blockers object to the removal (10 of 19 in the v5.2 runs).
  The text is constant across arms, so comparisons stand, but absolute
  rates on this fixture are affected (backlog #21).
- **Hedge demotion can demote true claims.** It fired once in the N=3
  measurement, on a hedged formulation of a genuine thread-safety
  finding. "Hedged" does not imply "wrong" (backlog #12).
- **Both agents' thinking sometimes runs away.** In seven telemetry
  runs, 6 of 42 first attempts ran away (4 reviewer, 2 engineer), at
  temperature 0.7 and 0.05 alike. Uncapped, they filled any window.
  Both engineer runaways were a persona-versus-blocker loop (#20). The
  one reviewer runaway with a tail read as an open-ended search for
  more issues, not a visible loop. All six retries recovered. With
  `NUM_PREDICT` a runaway still costs 3–5 minutes (#19). Before the
  telemetry, at 16384, it caused one AGENT_FAILURE in the N=3 (e4d1b3).
- **Retried rounds are a different mode.** The "Invalid JSON"
  correction makes the reviewer answer in 267–493 tokens with little or
  no thinking (`thinking_chars` 0 in 15cc3f). In the telemetry runs, 4
  of 21 reviewer rounds came from such retries; telemetry shows which.
  Score them separately; `eval_harness.round1 score` excludes them.
- **The output cap has a thin margin.** Finished reviewer replies reach
  10,097 tokens, ~18% under `NUM_PREDICT`. A legitimately longer reply
  would be cut and retried in the low-thinking mode.
- **Debates with reviewer blockers never converge.** Under j1 every
  archived debate ended at MAX_ROUNDS_EXCEEDED. j2 lets a blocker-free
  round converge, but 15 of the 16 records have reviewer blockers in
  every round, and nothing ends a debate early on a settled rejection
  (backlog #18).
- **Feedback anchors rather than tests,** and the live loop can undo
  retrieval's gains: in the pilot, engineer concerns reintroduced
  thread-safety blockers in round 3 after a clean round 1. Additional
  reason to score round-1 output (see backlog #11).
- Diff-only review caps recall. Partially mitigated by the context pack;
  the pack only carries what the indexer harvests.
- Reviewed code goes into the prompt unfenced (prompt-injection surface,
  backlog #11).
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
| `agent_client.py` | Ollama client. Single agent turn, JSON-mode enforcement, retries with corrective messages, optional per-attempt telemetry (token counts, thinking/reply sizes, done_reason, wall time; tails of failed replies). The ONLY module that touches the network. |
| `adjudication.py` | Pure adjudication logic, no I/O: `normalize_agent_output()`, `derive_verdict()`, `convergence_verdict()`, `demote_hedged_blockers()` (returns the output and the demoted count), `JUDGE_VERSION`. CI-importable. |
| `debate.py` | The debate loop. Transcript templates incl. `REPO_CONTEXT_TEMPLATE`; loads `repo_context.json`, calls `build_context_pack` (never fatal: errors degrade to no retrieval), injects retrieval into the transcript, records `repo_context_pack` (report, pack text, hash, index version) and per-round telemetry in decision records. Ends with AGENT_FAILURE on exhausted agent calls. `run_round1_review` is the measurement mode: the debate's first reviewer call alone, saved as a measurement record. |
| `golden_tests.py` | Golden suite: 3 LLM-backed model fixtures + `run_hedge_unit_tests()` (7 deterministic guardrail cases, production-derived texts). |
| `reviewer_prompt.py` | Single source of truth for agent system prompts. PROMPT_VERSION (currently v6-diff-authoritative). Also holds FAILURE_SENTINEL. |
| `file_metadata.py` | File-path → layer mapping and layer constraint notes. |
| `repo_context.py` | Offline indexer (`orchestrator.py --index ../qttune [--no-llm]`) AND debate-time retrieval (`harvest_callsites`, `build_context_pack`): modified-file purposes, referenced types/constants, queued-connection call sites with paren-depth statement scanning, budget-enforced truncation. Since v6, entries the diff removes are omitted and named, and the index records its source commit. Consumed by debate.py since v5-context-pack. |
| `repo_context.json` | Committed context pack for QtTune, built from the bridge fixture's base (`source_commit` `e0c4c31`, 2026-10-22: 35 files, 24 LLM purposes, 1 queued-connection call site). Reviewing a different diff needs an index of that diff's base. repo_root field removed 2026-10-13 (local-path leak). Read by debate.py at runtime from next to repo_context.py, regardless of CWD. |
| `eval_harness/probe.py` | FP-rate probe: N runs against a clean fixture. CLEAN / BORDERLINE / SYSTEMATIC / NO_DATA. |
| `eval_harness/bakeoff.py` | Side-by-side model comparison on bug + clean fixtures. |
| `eval_harness/round1.py` | Round-1 measurements. `run` collects samples through `debate.run_round1_review`, so unlike the probe and bake-off it uses agent_client and config. `score` counts M1 and lists M2 candidates over measurement or debate records, first attempts on one diff only. |
| `eval_harness/__init__.py` | Package marker. |
| `tests/test_deterministic.py` | Stdlib unittest regression suite: adjudication, agent client (incl. telemetry), debate (incl. retrieval in the transcript, record provenance, malformed-index degradation, round-1 measurement mode), eval scoring (incl. the round-1 scorer), indexer harvesting, CLI. Fake Ollama HTTP layer. CI-ready. |
| `tests/test_retrieval.py` | Retrieval unit tests: paren-depth scanning, multiline lambda connects, truncation-budget accounting, section headers, related call sites, identifier matching, call-site/type/purpose rendering. |
| `docs/decisions/0001-model-selection.md` | ADR-0001: model selection rationale, bake-off numbers. |
| `docs/decisions/0002-adjudication-and-fp-remediation.md` | ADR-0002: the false-positive arc — baseline triage, v1 guardrails, re-measurement, live-loop control, context-pack N=3 results with retroactive re-adjudication flag. |
| `docs/portability_guide.md` | Running on other machines / codebases. Predates the module split. |
| `docs/fixtures/qttune_bridge_refactor.diff` | Input diff for all bridge-refactor debates. Provenance (established 2026-10-13): reverse patch of QtTune `e0c4c31`; post-state identical to committed `8ffbf19` (blob `1c195f8`). |
| `coach_artifacts/decision_debate_*.json` | Decision records. Nine archived: header review (194320), baseline (203917), v1 re-measurement (014257), feedback smoke (153541, see erratum caveat), live-loop control (170208), context-pack pilot (201540, unscored), and three scored context-pack runs (203802, 204845, 210548). Plus seven unscored v5.2 telemetry runs on the bridge fixture, from 20261022: two at num_ctx 16384 (134539_3026b2, 140943_bbe168), three at 24576 (143424_1b11cc, 145342_743bc4, 153943_7a4809), and two at 24576 with num_predict 12288 (160429_15cc3f, 161800_5b3f1d). Records from 2026-10-10 on carry `prompt_fingerprint`, sampling settings, input hashes, layer, `agent_failures`; v5 records carry `repo_context_pack`; v5.2 records add the pack text and per-attempt `telemetry`. |
| `coach_artifacts/measurement_round1_*.json` | Round-1 measurement records (`metadata.mode` `round1_reviewer`): one reviewer round, no engineer, no merge decision. Same provenance fields as decision records. None committed yet. |
| `probe_logs/fp_*.json` | 5-run probe aggregates backing the FP-rate claims. |
| `requirements.txt` | Runtime deps (requests). |
| `.github/workflows/` | CI: compile checks + regression suite, no Ollama. |
| `.gitignore` | Transient outputs (gold_tests/run_*.json, repo_context_cache.json, *.bat) not committed. |

**Module dependency direction (acyclic):** reviewer_prompt + file_metadata
(leaves) → config → agent_client and adjudication (parallel layers) →
repo_context → debate + golden_tests → orchestrator. `tests/` sits on
top of everything.

---

## Conventions (do not silently violate)

1. **Derived verdicts only.** Never trust a model's self-reported
   verdict label. Judge reads blockers/questions/concerns arrays. A
   change to the judge or the convergence rule bumps `JUDGE_VERSION`.
2. **Fail closed.** Parse failure, schema violation, timeout, empty
   input → reject / manual review. Never default to approve.
3. **Blockers must be demonstrable.** Speculation belongs in questions.
   HEDGE_PATTERNS changes must keep the 7 hedge units passing.
4. **Prompts are versioned.** Any change to what agents see bumps
   PROMPT_VERSION. Transcript templates and the pack format are prompts
   too: a change to `build_context_pack`'s output also bumps
   `PACK_FORMAT_VERSION`, which feeds the fingerprint. Currently
   v6-diff-authoritative.
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

Suggested order as of 2026-10-22: v6 baseline on the bridge fixture
(predict first; ADR-0002, fifth measurement amendment; samples from
`eval_harness.round1`) → #15 if the
deletion class persists → #21 fixture proposal → #16 runaway output →
#12 hedge gate → #18 early reject → #11 transcript protocol → #17
re-triage → the rest.

1. **Repo context pack — DONE (2026-10-13).** Indexer, callsite
   harvester, debate-time retrieval and the third measurement are all
   landed (ADR-0002, fourth measurement). Kept for history; open
   follow-ups became #15–#17 below.
2. **Judge granularity rework — minimal option DONE (2026-10-22, j2).**
   A round converges as APPROVED_WITH_OPEN_QUESTIONS when neither agent
   has blockers. Still open: splitting severity from resolution.
3. **GitHub Actions CI — DONE (2026-10-13).**
4. **Per-debate cost/latency telemetry — DONE (2026-10-22).** Each
   round's `telemetry` holds one entry per agent attempt, failed ones
   included: prompt_eval_count, eval_count, thinking and content
   chars, done_reason, prompt chars, wall time and outcome. Failed
   attempts also keep the tail of their thinking and content.
   prompt_eval_count near NUM_CTX means the prompt is crowding the
   window. A large eval_count with done_reason=length means the output
   ran out. Probe and bake-off do not record it (#9).
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
11. **Transcript protocol** (one versioned prompt change, predicted
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
15. **Deletion-hallucination remediation.** Ground
    "removed symbols" from the diff's minus side: a blocker claiming a
    surviving reference to symbol X must verify X is not in the removed
    set. Deterministic pre-judge check in adjudication.py, or retrieval
    that lists removed symbols alongside survivors. Predict + measure
    per convention 7. In the v5.2 runs every instance cited a symbol
    the stale pack asserted; v6 now omits those from the pack. Do this
    only if the v6 baseline still shows the class.
16. **Context budget and runaway output — IN PROGRESS (2026-10-22).**
    - **Prompt side, settled:** the prompt is a stable ~9.4K–10.2K
      tokens. The diff is ~83% of it, the pack ~820 tokens, feedback
      ~400 per round. Dropping the pack is not worth it.
    - **NUM_CTX 24576, kept:** it finished two replies (7.7K and 10.1K
      output tokens) that 16384 would have lost.
    - **Output capped, verified.** Both engineer runaways caught with
      diagnostics (7a4809, 15cc3f) cycled between the persona and the
      blocker rule. `NUM_PREDICT` 12288 now caps every attempt, above
      every finished reply so far. Live, two runaways stopped at exactly
      12,288 tokens and both retries recovered (ADR-0002, third
      follow-up and verification).
    - **Still open: the reviewer's runaways.** The one with a tail
      (15cc3f) read as an open-ended search for more issues, not a
      visible loop; a cycle longer than the 400-char tail cannot be ruled
      out. A repetition measure over the whole thinking, or a longer
      tail, would settle it. Stopping loops early is #19; the engineer
      prompt conflict is #20.
17. **Historical re-triage (NEW).** Re-read the v1 (014257) and
    control (170208) thread-safety blockers against the fixture's
    actual post-state (which does read m_currentFrameCount on the
    worker thread); correct the FP/TP labels in ADR-0002 and the
    README precision table. The re-adjudication flag is already
    recorded; this executes it.
18. **Early-reject termination (design, not code).** Filed 2026-10-22
    from the 2026-10-21 STATUS note, with code review 2026-10-21 finding
    7 applied. Goal: end a debate as `CONVERGED_REJECT - BLOCKED` when
    the rejection is settled, instead of running to
    MAX_ROUNDS_EXCEEDED. Both options are judge-only, in
    adjudication.py, with no prompt change, and agent failures keep
    precedence.
    - *Option A:* both derived verdicts are `reject`.
    - *Option B:* a reviewer blocker and an engineer concern or question
      share an identifier token (`m_currentFrameCount`) and a
      failure-class term (race, starv, deadlock, leak, overflow,
      use-after-free). Record the matched pair for triage.

    Constraints:
    - **Round-1 agreement only.** From round 2 on, each agent reads the
      other's findings in REVISE ADDRESSING, and the records show echo.
      In 153541, the engineer's round-2 blockers restate the reviewer's
      round-1 blockers nearly verbatim. In ff958c, engineer concerns
      return as reviewer blockers in round 3. Later-round overlap would
      end debates on echoed claims, including echoed false positives.
      Neither option is free of false convergence.
    - **Option A alone does nothing in round 1.** The engineer had zero
      round-1 blockers in all nine archived records, so only Option B
      can fire.
    - **#2 first — done (j2, 2026-10-22).** The engineer returned
      concerns in all 25 completed engineer rounds on record, so no
      debate could converge whatever the reviewer said. #2's minimal
      rule was the root fix. #18 only adds early exits for the 7 of 8
      manual reviews that ended with reviewer blockers. The eighth,
      header review 194320, had no blockers on either side; under j2 it
      converges in round 1. Option A and B's checks belong in
      `adjudication.convergence_verdict`.
    - **Verdict labels stay out of feedback.** Agents do not see each
      other's verdict text. Feedback carries the reviewer's blockers
      and the engineer's concerns and questions. The judge ignores
      labels, so adding them would add anchoring without information.
    - **Option C** (uphold-or-withdraw) is #11.
19. **Stop looping replies early (NEW, 2026-10-22).** A runaway spends
    ~12K tokens and 3–5 minutes going in circles before `NUM_PREDICT`
    stops it. Stream the reply in agent_client.py and abort once the
    recent thinking repeats an earlier passage, then retry as usual.
    Most of a runaway's time would be saved. Watch for false positives
    on legitimately repetitive reasoning; the telemetry tails give test
    material. This catches the engineer's loops. It may miss the
    reviewer's runaway, which looked like an open-ended search rather
    than repetition (#16).
20. **Engineer prompt conflict (NEW, 2026-10-22).** Both engineer
    runaways on record (7a4809, 15cc3f) alternated between "argue for
    shipping velocity; correctness is the reviewer's job" and "a
    demonstrable violation is a blocker". Say what the engineer should do when it
    sees a correctness violation, e.g. report it as a concern for the
    reviewer. This is a prompt change: bump PROMPT_VERSION and measure
    per convention 6.
21. **Bridge fixture proposal mismatch (NEW, 2026-10-22).** The
    proposal text describes `e0c4c31` adding the LiveView feature; the
    fixture diff is its reverse and removes it (ADR-0002, fifth
    measurement). Keep the text for the v6 baseline, so that it
    compares with every earlier run. Afterwards, decide
    whether new fixture runs use a matching proposal, e.g. *"Revert
    e0c4c31: remove coalesced signal updates and the LiveView page"*.
    That breaks comparability with every earlier run, so treat it as a
    new baseline (predict, then measure). The stable corpus (#7) should
    take its proposal text from the diff's actual direction.

Deliberately deferred: MAX_DEBATE_ROUNDS / loop-shape tuning — #2
supersedes.
