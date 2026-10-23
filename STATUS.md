# STATUS — Project Map & Backlog

Last updated: 2026-10-22. That day, in order:
- record provenance and per-attempt telemetry;
- context window raised to 24576 and output capped at 12288;
- v6 diff-authoritative retrieval;
- backlog #18–#21 filed;
- convergence rule j2;
- the round-1 measurement mode and scorer;
- the v6 baseline;
- evidence-quoted blockers shipped as v9 / j4, after arms H, G and G3;
- CI confirmed green on Python 3.11 and 3.13 (`32e6209`);
- code review 2026-10-21 items closed out;
- the review's simplifications: one shared diff reader (judge j5) and
  `run_debate`'s round split into helpers, with no change to any request
  or record on the bridge fixture;
- the hedge check reads a reviewer blocker without its quoted code
  (judge j6); no recorded result changes;
- backlog #12 closed: a hedged blocker is never exempt;
- the transcript protocol measured (ADR-0002, eleventh measurement) and
  shipped in part as v10.1: the reviewed code is fenced as data, while
  the feedback stays v9's;
- `1dbe31b` pushed, CI green on 3.11 and 3.13; the docs, the backlog
  and the code review re-checked against it.

2026-10-23 (code review 2026-10-23, findings 13–18; `6f020f2`):
- judge j7: empty and oversized input refused before any model call,
  and diff lines outside any file header made evidence; no recorded
  result changes (ADR-0002, "Input Checks j7");
- the golden suite routed through a debate's round-1 reviewer path
  (backlog #14, first half; ADR-0002, "Golden Suite Routing");
- the index records each file's git blob id, and retrieval warns when
  the diff starts from another version (committed index rebuilt, zero
  model calls);
- the review's housekeeping items.

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
- Hedge-language demotion guardrail (deterministic, regression-tested).
  Since judge j6 (2026-10-22) it reads a reviewer blocker without its
  quote, so hedge words in quoted code don't count.
- Golden suite: 3 model fixtures + 7 deterministic guardrail units = 10/10
  (re-run live 2026-10-10 after the fixes below). Since 2026-10-23 the
  fixtures go through a debate's round-1 reviewer path, evidence check
  included; not yet run live that way.
- Deterministic regression suite: 149 stdlib unittest cases in `tests/`,
  with Ollama faked at the HTTP layer. No model needed; CI-ready.
- FP-rate probe (5-run aggregates), model bake-off
- Repo indexer (`--index`): typedefs, constants, layer map, LLM purpose
  summaries and queued-connection call sites for QtTune. The index
  records the commit it was built from and each file's git blob id. The
  committed index was rebuilt 2026-10-22 from QtTune `e0c4c31`, the
  bridge fixture's base: 35 files, 24/24 source purposes, 7 types, 10
  constants, 1 call site. It was rebuilt again on 2026-10-23 to add the
  blob ids, identical otherwise, with zero model calls. Earlier builds
  used `6b58c3a`, a later tree than the fixture.
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
  `requirements.txt` and runs on Python 3.11 and 3.13. Both jobs pass
  (`ed8d31d`, `32e6209` and `1dbe31b`); 3.11 is not installed locally,
  so CI is the only check on it.
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
  grew from 2,023 to 2,816 chars. Precision was scored on the six
  scorable 2026-10-22 telemetry runs below (ADR-0002, fifth
  measurement, arm 1).
- **Provenance and telemetry (2026-10-22, PROMPT_VERSION
  v5.2-pack-sections; code review 2026-10-21 findings 5, 6, 8).**
  - Records keep the exact pack text, its SHA-256, the index version and
    `PACK_FORMAT_VERSION` under `repo_context_pack`.
  - `prompt_fingerprint` hashes templates only, plus
    `REPO_CONTEXT_TEMPLATE` and `PACK_FORMAT_VERSION` when a pack was
    used. Runs of one prompt on different diffs now share a fingerprint.
  - Each round records `telemetry`: one entry per agent attempt with
    `prompt_eval_count`, `eval_count`, thinking and reply sizes,
    `done_reason`, prompt chars, wall time and outcome.
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
    purposes are annotated.
  - **Measured 2026-10-22** (ADR-0002, sixth measurement; 10 round-1
    samples, all first attempts, 26 blockers):
    - Deletion-consistency FPs held at 0.5 per run, against a predicted
      ≤ 0.2. They no longer cite pack-asserted symbols.
    - The `m_currentFrameCount` race appeared in 5 of 10 runs.
    - 4 blockers in 3 runs correctly flag that the diff reverts
      `e0c4c31`'s in-flight backpressure gate. Arm 1 had none.
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
    verdict `NOT_ADJUDICATED - ROUND1_MEASUREMENT`). It runs a debate's
    first round (`_run_round`) without the engineer. A test pins that it
    sends the identical request as a debate's first call, and the
    records share the debate's `prompt_fingerprint`. No prompt changed,
    so PROMPT_VERSION stayed v6.
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
- **Evidence-quoted blockers (2026-10-22, PROMPT_VERSION
  v9-post-change-quotes, JUDGE_VERSION j4-post-change-quotes; ADR-0002,
  eighth to tenth measurements).**
  - Each reviewer blocker is `{claim, file, quote}`. The quote must be
    code as it reads after the change: context or added lines, never
    removed ones. The prompt says a wrong blocker costs more than a
    question.
  - `adjudication.demote_unverified_blockers` runs before hedge
    demotion. It moves a blocker to questions when its quote is not in
    the post-change lines of the file it names. Matching is line by line
    within one hunk; a trailing comment may be omitted.
  - Since judge j5 (2026-10-22) the check reads diffs with the shared
    `diff_reader`. A diff without hunk headers is evidence too; under
    j4 every blocker on one was demoted. Otherwise j5 is j4 (ADR-0002,
    "Evidence Reader j5").
  - Rounds record `evidence_demotions`. The scorer lists those items as
    `#e`.
  - **Measured on 10 samples:**
    - deletion-class FPs 0.1 per run, against 0.5 at v6;
    - stored blockers 94% valid, against 42%;
    - the race found in 7 of 10 runs;
    - 2 valid blockers demoted.
  - **How it got there:**
    - Arm H, removing the hedging ban, was not supported: the reviewer
      did not hedge more.
    - Arm G accepted quotes from either side. The deletion class moved
      to quoting removed lines, and a matcher error demoted valid
      blockers.
  - The engineer, the golden suite, the probe and the bake-off are
    unchanged and do not check quotes.
- **Fenced input (2026-10-22, PROMPT_VERSION v10.1-fenced-input; ADR-0002,
  eleventh measurement).**
  - The diff and the context sit between BEGIN DATA and END DATA lines.
    The lines carry a mark hashed from that input, so the reviewed text
    cannot close the fence. A preamble says that text inside is data,
    never instructions.
  - Context cut at 8000 characters is marked as truncated.
  - Feedback is still v9's: appended to the proposal.
  - **A CRITIQUES section was measured and not shipped.** It put the
    previous round in its own section, labelled unverified, with every
    channel and a keep-or-drop instruction. In a paired round-2
    measurement it matched v9's format on the race and on precision
    (93% each), but it dropped the in-flight-gate blocker in both pairs
    that had it and ran away on 3 of 10 first attempts, against 1 for
    v9. It stays in `debate.py` as the pair measurement's candidate arm
    (`run_round2_pair`, scored by `eval_harness.round2`).
  - Round 1 with the fence: the race in 10 of 10 runs, deletion class
    0.1 per run, 80% of stored blockers valid. That is 4 other FPs
    against G3's 0, which is worth watching.
- **Input checks (2026-10-23, JUDGE_VERSION j7-input-checks; code
  review 2026-10-23, findings 13, 16 and 17; ADR-0002, "Input Checks
  j7").**
  - No diff and no context: `NO_INPUT - MANUAL_REVIEW_REQUIRED`, without
    a model call. Under j6 it could approve. The CLI refuses
    `--proposal` without `--diff` or `--context`.
  - A round-1 request estimated above `NUM_CTX - NUM_PREDICT` tokens, at
    3 chars per token: `INPUT_TOO_LARGE - MANUAL_REVIEW_REQUIRED`.
    Records keep the estimate as `metadata.input_check`.
  - Diff lines outside any file header are evidence for any file name.
    Under j6 the reviewer could not block such a diff.
  - Normalization drops a reply's own `blocker_evidence`. A non-string
    reply body is a malformed response, not a crash.
  - The measurement batches stop on refused input, and the scorers skip
    records without a round.
  - Five fake-driven runs on the bridge fixture sent byte-identical
    requests before and after.
- **Golden suite routing (2026-10-23, backlog #14 first half; ADR-0002,
  "Golden Suite Routing").** Each fixture is the CODE CONTEXT of a
  debate's round-1 reviewer call (`debate.review_round1`): fenced, with
  its layer note, and the evidence and hedge checks applied. A neutral
  proposal is used, and the first attempt stays at 0.05 (the user's
  choice). The run log records the versions, model and temperature.
- **Index-base check (2026-10-23; code review 2026-10-23, finding
  15).** The index stores each file's git blob id. Retrieval compares it
  with the diff's `index <before>..<after>` lines. On a mismatch it
  warns on stderr and records the files under
  `repo_context_pack.base_check`, and returns `index_base_mismatch`. The
  pack itself is unchanged (the user's choice). On the bridge fixture all
  6 base blobs match the committed index.

**Known limitations (by design or pending):**
- **Diffs above about 30K chars are refused** at `NUM_CTX` 24576 and
  `NUM_PREDICT` 12288, with the bridge fixture's prompt and pack. That
  fixture is 26.7K chars. Raising `NUM_CTX` moves the limit; ADR-0001
  has the hardware constraints.
- **Deletion hallucination: the reviewer fabricates surviving
  references to code the diff removes.** It was the dominant FP class
  in the v5 N=3 (8 total, 6/0/1 by run). In six scorable v5.2 runs it
  fell to 3 (0.5 per run), every one citing a symbol the stale context
  pack asserts. One cites a line number that exists only in the indexed
  tree (ADR-0002, fifth measurement, arm 1). v6 fixes the retrieval
  side: the diff is authoritative and removed entries are omitted.
  **The v6 baseline (10 samples, 2026-10-22) shows the class persists
  at the same rate,** 5 in 10 runs (0.5 per run). Four of the five claim
  that `Main.qml` still references `signalModel`. No pack contains that
  name, and `Main.qml` never did: it was used only in the deleted
  `LiveViewPage.qml`. So the class does not need the pack (ADR-0002,
  sixth measurement).
  **Since v9 / j4 the judge removes most of it** (0.1 per run stored).
  The model still produces 3–4 per 10 runs, which are demoted because
  their quotes exist only on the removed side.
- **A quote proves the code exists, not that it supports the claim.**
  The one deletion-class blocker G3 kept quoted unrelated post-change
  code (ADR-0002, tenth measurement).
- **A deleted test cannot be a blocker since j4.** Its lines exist only
  on the removed side, so "this diff deletes the regression test"
  becomes a question.
- **The bridge fixture's proposal contradicts its diff.** Every run
  since 2026-10-07 used *"Review: coalesced signal updates with
  LiveView Page v0.3.0 phase 2"*, the subject of `e0c4c31`, which adds
  the LiveView page. The fixture is its reverse and deletes it. Many
  round-1 blockers object to the removal (10 of 19 in the v5.2 runs,
  13 of 26 in the v6 baseline).
  The text is constant across arms, so comparisons stand, but absolute
  rates on this fixture are affected (backlog #21).
- **Hedge demotion demotes true claims too, by design.** It fired once
  in the N=3 measurement, on a hedged formulation of a genuine
  thread-safety finding. "Hedged" does not imply "wrong", but a reviewer
  that hedges has not shown a violation, so the claim is a question
  (decided 2026-10-22, ADR-0002, "Hedge Check j6"). It stays visible:
  the verdict is APPROVED_WITH_OPEN_QUESTIONS, not a clean approval.
- **Both agents' thinking sometimes runs away.** In seven telemetry
  runs, 6 of 42 first attempts ran away (4 reviewer, 2 engineer), at
  temperature 0.7 and 0.05 alike. Uncapped, they filled any window.
  Both engineer runaways were a persona-versus-blocker loop (#20). The
  one reviewer runaway with a tail read as an open-ended search for
  more issues, not a visible loop. All six retries recovered. With
  `NUM_PREDICT` a runaway still costs 3–5 minutes (#19). Before the
  telemetry, at 16384, it caused one AGENT_FAILURE in the N=3 (e4d1b3).
  In the eleventh measurement, 0 of 20 round-1 first attempts ran away,
  against 4 of 20 round-2 reviewer first attempts: 3 with the candidate
  CRITIQUES section and 1 with v9's feedback. Their tails were
  open-ended re-checking.
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
  reason to score round-1 output (see backlog #11). In round 2 the
  reviewer mostly repeats itself: 39 of 41 round-2 blockers in the 15
  archived debates that reached round 2 carried round-1 subjects, and
  all 29 in the eleventh measurement's 6 pairs did.
- Diff-only review caps recall. Partially mitigated by the context pack;
  the pack only carries what the indexer harvests.
- Since v10.1 the reviewed code is fenced as data. Feedback still goes
  into the proposal, where it reads as the author's text (backlog #11).
- Multi-file diffs only inject the FIRST file's layer. Queued (#8).
- Golden model fixtures are nondeterministic. Use `tests/` for
  pass/fail signals.
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
| `orchestrator.py` | Thin CLI entrypoint: argument parsing and dispatch only. Modes `--golden`, `--proposal` and `--index` are mutually exclusive; `--proposal` needs `--diff` or `--context`; inputs read as UTF-8. Re-exports key symbols as a transition shim. |
| `config.py` | Central configuration: MODELS dict, num_ctx, the output cap, the input check's chars-per-token floor, timeouts, temperatures, and prompt composition. Single place to swap models (probe and bake-off excepted). |
| `agent_client.py` | Ollama client. Single agent turn, JSON-mode enforcement, retries with corrective messages, optional per-attempt telemetry (token counts, thinking/reply sizes, done_reason, wall time; tails of failed replies). Holds `FAILURE_SENTINEL`; retry notes are warnings on the `agent_client` logger. The ONLY module that touches the network. |
| `adjudication.py` | Pure adjudication logic, no I/O: every final verdict string, `normalize_agent_output()` (keeps reviewer blockers' file, quote and claim as `blocker_evidence`, and drops a reply's own), `derive_verdict()`, `convergence_verdict()`, `evidence_sources()` and `demote_unverified_blockers()` (quotes must be post-change code; since j7 lines outside any file header count for any file), `demote_hedged_blockers()` (judge j6: reads a reviewer blocker without its quote; both demotions return the output and the demoted count), `JUDGE_VERSION`. CI-importable. |
| `diff_reader.py` | The one unified-diff reader, pure: `read_diff()` yields headers, hunk headers and context/removed/added lines, counted by hunk length inside a hunk and read by first character outside one; `diff_paths()` lists the post-change paths; `base_blobs()` reads git's pre-change blob ids. Used by the evidence check, retrieval and its index-base check, and layer identification. |
| `debate.py` | The debate loop. Transcript templates incl. `REPO_CONTEXT_TEMPLATE`; loads `repo_context.json`, calls `build_context_pack` (never fatal: errors degrade to no retrieval), injects retrieval into the transcript, records `repo_context_pack` (report, pack text, hash, index version, base check) and per-round telemetry in decision records. `_input_check` refuses empty or oversized input before any model call (j7). The transcript fences the diff and context as data (v10.1). A round is `_run_round` (agent calls, then guardrails) and `_judge`. Applies the evidence check and then hedge demotion to reviewer replies, and records `evidence_demotions` and `hedge_demotions` per round. Ends with AGENT_FAILURE on exhausted agent calls. Two measurement modes: `run_round1_review`, the debate's first reviewer call alone, and `run_round2_pair`, which compares the candidate CRITIQUES section with a debate's own feedback in round 2. `review_round1` is the golden suite's unsaved round-1 reviewer call. |
| `golden_tests.py` | Golden suite: 3 LLM-backed model fixtures + `run_hedge_unit_tests()` (7 deterministic guardrail cases, production-derived texts). Since 2026-10-23 each fixture is reviewed through `debate.review_round1` at 0.05, evidence check included; not yet run live that way. |
| `reviewer_prompt.py` | Single source of truth for agent system prompts. PROMPT_VERSION (currently v10.1-fenced-input: reviewer blockers are `{claim, file, quote}`, and the transcript fences the reviewed code; the templates are in debate.py). |
| `file_metadata.py` | File-path → layer mapping and layer constraint notes. |
| `repo_context.py` | Offline indexer (`orchestrator.py --index ../qttune [--no-llm]`) AND debate-time retrieval (`harvest_callsites`, `build_context_pack`): modified-file purposes, referenced types/constants, queued-connection call sites with paren-depth statement scanning, budget-enforced truncation. Since v6, entries the diff removes are omitted and named, and the index records its source commit. Since 2026-10-23 it records each file's git blob id, and retrieval checks the diff's base against them; the report counts matched and shown entries per section. Consumed by debate.py since v5-context-pack. |
| `repo_context.json` | Committed context pack for QtTune, built from the bridge fixture's base (`source_commit` `e0c4c31`, 2026-10-22: 35 files, 24 LLM purposes, 1 queued-connection call site; rebuilt 2026-10-23 to add blob ids). Reviewing a different diff needs an index of that diff's base; a debate warns when the diff's base blobs differ. repo_root field removed 2026-10-13 (local-path leak). Read by debate.py at runtime from next to repo_context.py, regardless of CWD. |
| `eval_harness/probe.py` | FP-rate probe: N runs against a clean fixture. CLEAN / BORDERLINE / SYSTEMATIC / NO_DATA. |
| `eval_harness/bakeoff.py` | Side-by-side model comparison on bug + clean fixtures. |
| `eval_harness/round1.py` | Round-1 measurements. `run` collects samples through `debate.run_round1_review`, so unlike the probe and bake-off it uses agent_client and config. `score` counts M1 and lists M2 candidates over measurement or debate records, first attempts on one diff only, and lists evidence-demoted (`#e`) and hedge-demoted (`#h`) items separately. |
| `eval_harness/round2.py` | The round-2 pair measurement. `run` collects samples through `debate.run_round2_pair`: a debate's round 1, then the round-2 reviewer twice on the same round-1 replies, once with the candidate CRITIQUES section and once with a debate's own feedback. `score` compares the arms on first-attempt pairs and tags each round-2 blocker carried, from-question, echo? or new, from its claim's identifiers. |
| `eval_harness/__init__.py` | Package marker. |
| `tests/test_deterministic.py` | Stdlib unittest regression suite: adjudication, agent client (incl. telemetry and log records), diff reading (incl. base blobs), the evidence check and hedge check, debate (incl. the input checks, retrieval in the transcript, the index-base warning, record provenance, malformed-index degradation, round-1 measurement mode, demotion order, the fence, the round-2 pair mode, the golden suite's path), eval scoring (incl. the round-1 and round-2 scorers), indexer harvesting, CLI. Fake Ollama HTTP layer. CI-ready. |
| `tests/test_retrieval.py` | Retrieval unit tests: paren-depth scanning, multiline lambda connects, truncation-budget accounting, matched and shown counts, section headers, related call sites, identifier matching, call-site/type/purpose rendering. |
| `docs/decisions/0001-model-selection.md` | ADR-0001: model selection rationale, bake-off numbers. |
| `docs/decisions/0002-adjudication-and-fp-remediation.md` | ADR-0002: the false-positive arc. Baseline triage, v1 guardrails, re-measurement, live-loop control, and context-pack N=3 results with the retroactive re-adjudication flag. Then the round-1 measurements (fifth to tenth: diff-authoritative retrieval, the hedging ban, evidence quotes), the judge versions j2 to j6, and the eleventh measurement (the transcript protocol, shipped as the fence only). |
| `docs/design.md` | The pipeline, outcomes, code layout and key design decisions, for readers who want depth after the README. |
| `docs/results.md` | The measured precision story, its costs, the evidence files and how to reproduce them. Summarizes ADR-0002. |
| `docs/usage.md` | Every command: tests, reviews, golden suite, indexer, eval harness, reading a record. |
| `docs/portability_guide.md` | Adapting the tribunal to other codebases. Model keys and troubleshooting corrected 2026-10-23; the walkthrough is illustrative. |
| `docs/fixtures/qttune_bridge_refactor.diff` | Input diff for all bridge-refactor debates. Provenance (established 2026-10-13): reverse patch of QtTune `e0c4c31`; post-state identical to committed `8ffbf19` (blob `1c195f8`). |
| `coach_artifacts/decision_debate_*.json` | Decision records. Nine archived: header review (194320), baseline (203917), v1 re-measurement (014257), feedback smoke (153541, see erratum caveat), live-loop control (170208), context-pack pilot (201540, unscored), and three scored context-pack runs (203802, 204845, 210548). Plus seven v5.2 telemetry runs on the bridge fixture, from 20261022, whose six scorable round 1s are the fifth measurement's arm 1: two at num_ctx 16384 (134539_3026b2, 140943_bbe168), three at 24576 (143424_1b11cc, 145342_743bc4, 153943_7a4809), and two at 24576 with num_predict 12288 (160429_15cc3f, 161800_5b3f1d). Records from 2026-10-10 on carry `prompt_fingerprint`, sampling settings, input hashes, layer, `agent_failures`; v5 records carry `repo_context_pack`; v5.2 records add the pack text and per-attempt `telemetry`. |
| `coach_artifacts/measurement_round1_*.json` | Round-1 measurement records (`metadata.mode` `round1_reviewer`): one reviewer round, no engineer, no merge decision. Same provenance fields as decision records. Forty, all on input fixture `docs/fixtures/qttune_bridge_refactor.diff`. The v6 baseline: 2026-10-22, 205145_5d2fc3 to 210647_dc4008. Arm H (v7): `20261022_22*`. Arm G (v8 / j3): `20261023_00*`. Arm G3 (v9 / j4): `20261023_01*`. |
| `coach_artifacts/measurement_round2_*.json` | Round-2 pair records (`metadata.mode` `round2_pair`): round 1 as `round_history`, the two round-2 reviewer replies under `outputs.round2_arms`. Ten, from the eleventh measurement (v10), `20261023_03*` and `20261023_04*` (UTC), on the bridge fixture. Their round 1 also scores as round-1 samples. |
| `probe_logs/fp_*.json` | 5-run probe aggregates backing the FP-rate claims. |
| `requirements.txt` | Runtime deps (requests). |
| `.github/workflows/` | CI: compile checks + regression suite, no Ollama. |
| `.gitignore` | Transient outputs (gold_tests/run_*.json, repo_context_cache.json, *.bat) not committed. |

**Module dependency direction (acyclic):** reviewer_prompt, file_metadata
and diff_reader (leaves) → config → agent_client and adjudication (parallel layers) →
repo_context → debate → golden_tests → orchestrator; debate →
eval_harness.round1 and eval_harness.round2 (which also uses round1's
helpers). `tests/` sits on top of everything. probe.py and
bakeoff.py import only reviewer_prompt.

---

## Conventions (do not silently violate)

1. **Derived verdicts only.** Never trust a model's self-reported
   verdict label. Judge reads blockers/questions/concerns arrays. A
   change to the judge or the convergence rule bumps `JUDGE_VERSION`.
2. **Fail closed.** Parse failure, schema violation, timeout, empty
   input → reject / manual review. Never default to approve. Since j7
   empty or oversized input is refused before any model call.
3. **Blockers must be demonstrable.** Speculation belongs in questions.
   A hedged blocker is never a blocker, even with a verified quote or a
   line citation (decided 2026-10-22).
   HEDGE_PATTERNS changes must keep the 7 hedge units passing.
4. **Prompts are versioned.** Any change to what agents see bumps
   PROMPT_VERSION. Transcript templates and the pack format are prompts
   too: a change to `build_context_pack`'s output also bumps
   `PACK_FORMAT_VERSION`, which feeds the fingerprint. Currently
   v10.1-fenced-input.
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

Suggested order as of 2026-10-23 (j7 and the golden routing done; code
review 2026-10-23): run the live golden suite (its prediction is in
ADR-0002, "Golden Suite Routing") → #7 stable corpus, so the evidence
check's precision is tested beyond one fixture; the index-base warning
and the size limit are in place for it → #21 fixture proposal →
#16 runaway output → #18 early reject → #17 re-triage → #11 feedback
section → the rest.

Done items are removed (#1, #3, #4, #5, #12 and #15 so far); their history
is in Current State, the ADRs and git. Numbers are not reused, so
references elsewhere stay valid.

- **#2 Judge granularity: split severity from resolution.** The minimal
   option shipped as judge j2 (2026-10-22): a round with no blockers
   converges as APPROVED_WITH_OPEN_QUESTIONS.
- **#6 Chained/escalated debates.** On MAX_ROUNDS_EXCEEDED, re-submit
   unresolved questions as a fresh debate. Depends on #2.
- **#7 Stable real-diff corpus.** 3–5 triaged real diffs with known
   expected outcomes. The reverse-of-merged-commit technique that
   produced the current fixture is a repeatable way to build this.
- **#8 Multi-file diff layer handling.** Inject a layer map keyed by
   file; `diff_reader.diff_paths` already lists every changed path.
- **#9 Retire the orchestrator re-export shim.**
- **#10 Codebase abstraction.** Move QtTune-specific bits behind config.
- **#11 Feedback section.** The fence and the truncation marker
    shipped as v10.1. Still open: move the prior round's critiques out
    of the proposal. The v10 CRITIQUES section is in `debate.py` as the
    pair measurement's candidate arm. A revision must hold the eleventh
    measurement's two lessons:
    - a defect caused by a removal, like the in-flight gate, must stay
      quotable as a blocker;
    - the instruction must not invite open-ended re-checking, which ran
      away 3 times in 10.

    Measure it with `eval_harness.round2` against a debate's own
    feedback.
- **#13 Evidence-trail repair.** Commit QtTune's core.h under
    docs/fixtures; rerun the probe with fixed scoring; correct
    ADR-0001's timeout row.
- **#14 Client hardening.** Pass the JSON schema as Ollama's `format`
    (structured outputs). That changes how replies are sampled, so
    predict and measure it. The other half, routing the golden fixtures
    through the transcript builder, was done on 2026-10-23.
- **#16 Context budget and runaway output — IN PROGRESS (2026-10-22).**
    Settled (Current State; ADR-0002, third follow-up and
    verification): the prompt is ~9.4K–10.2K tokens, ~83% of it the
    diff, so dropping the ~820-token pack is not worth it. `NUM_CTX`
    stays 24576, and `NUM_PREDICT` 12288 caps every attempt.
    - **Still open: the reviewer's runaways.** The one with a tail
      (15cc3f) read as an open-ended search for more issues, not a
      visible loop; a cycle longer than the 400-char tail cannot be ruled
      out. A repetition measure over the whole thinking, or a longer
      tail, would settle it. Stopping loops early is #19; the engineer
      prompt conflict is #20.
    - **New data (eleventh measurement):** the round-2 reviewer ran away
      on 4 of 20 first attempts, and round 1 on 0 of 20. The tails were
      open-ended re-checking ("Let me also check…"), not repetition.
- **#17 Historical re-triage.** Re-read the v1 (014257) and
    control (170208) thread-safety blockers against the fixture's
    actual post-state (which does read m_currentFrameCount on the
    worker thread); correct the FP/TP labels in ADR-0002 and the
    precision table in docs/results.md. The re-adjudication flag is already
    recorded; this executes it.
- **#18 Early-reject termination (design, not code).** Filed 2026-10-22
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
      round-1 blockers in all 19 records with an engineer round 1 (the
      nine archived debates and the eleventh measurement's 10 samples),
      so only Option B can fire.
    - **#2 first — done (j2, 2026-10-22).** The engineer returned
      concerns in all 35 completed engineer rounds on record, so no
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
- **#19 Stop looping replies early (filed 2026-10-22).** A runaway spends
    ~12K tokens and 3–5 minutes going in circles before `NUM_PREDICT`
    stops it. Stream the reply in agent_client.py and abort once the
    recent thinking repeats an earlier passage, then retry as usual.
    Most of a runaway's time would be saved. Watch for false positives
    on legitimately repetitive reasoning; the telemetry tails give test
    material. This catches the engineer's loops. It may miss the
    reviewer's runaway, which looked like an open-ended search rather
    than repetition (#16).
- **#20 Engineer prompt conflict (filed 2026-10-22; deferred by the
    user).** Both engineer runaways on record (7a4809, 15cc3f) alternated
    between "argue for shipping velocity; correctness is the reviewer's
    job" and "a demonstrable violation is a blocker". Say what the
    engineer should do when it sees a correctness violation, e.g. report
    it as a concern for the reviewer. This is a prompt change: bump
    PROMPT_VERSION and measure per convention 6. The engineer did not run
    away in the eleventh measurement's 10 round-1 calls.
- **#21 Bridge fixture proposal mismatch (filed 2026-10-22).** The
    proposal text describes `e0c4c31` adding the LiveView feature; the
    fixture diff is its reverse and removes it (ADR-0002, fifth
    measurement). The text was kept through the eleventh measurement,
    so every run compares with every earlier one. Decide whether new
    fixture runs use a matching proposal, e.g. *"Revert
    e0c4c31: remove coalesced signal updates and the LiveView page"*.
    That breaks comparability with every earlier run, so treat it as a
    new baseline (predict, then measure). The stable corpus (#7) should
    take its proposal text from the diff's actual direction.

Deliberately deferred: MAX_DEBATE_ROUNDS / loop-shape tuning — #2
supersedes.
