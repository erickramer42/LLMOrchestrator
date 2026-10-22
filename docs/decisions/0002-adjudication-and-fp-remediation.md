# ADR-0002: Rule-Based Adjudication and False-Positive Remediation

Date: 2026-10-13
Status: Accepted (v1 remediation validated by re-measurement; live-loop
control run 2026-10-13; context-pack measurement N=3 recorded 2026-10-13)

Supersedes the adjudication portions of ADR-0001.

## Context

On its first real workload — a 300-line QtTune bridge refactor — the
tribunal's reviewer produced 12 blockers, of which post-hoc triage against
actual source confirmed exactly 1 real defect: precision 1/12 (~8%),
despite 0/5 false positives on the clean-header fixture probe.

The fixture-vs-production gap is the central eval finding of this project:
synthetic-fixture success did not transfer to real workloads.

Decision record: `coach_artifacts/decision_debate_20261007_203917.json`
Input: `docs/fixtures/qttune_bridge_refactor.diff`

## Blocker Triage (original run, 2026-10-07)

| Class | Count | Examples | Disposition |
|---|---|---|---|
| Layer-rule misapplication | 7 | Qt-header includes in qttunebridge.h/.cpp | FP: bridge is app-layer; CMake FATAL_ERRORs on Qt in qttune-core |
| Definition-context guessing | 3 | "frame->data may reference freed stack memory"; anon-struct ABI worry | FP: qttune_frame_t has inline uint8_t data[64] — struct copy IS a deep copy; anon typedef is legal C |
| Pedantic over-promotion | 1 | m_lastReportedDropped non-atomic | FP: GUI-thread-only mirror paired with atomic counter is the correct pattern |
| Real defect | 1 | qttune_decode_signal(..., 8, ...) ignores frame->data_length | Confirmed — latent under mock transport (always 8 bytes), breaks for CAN-FD. Fixed in QtTune. |

Missed by the review (found by source-level triage): dropped-frame
report starvation under saturation; last-write-wins in the staging
buffer coalescing path. Diff-only review without full-repo context has
a blind spot that cuts both ways.

**Key diagnostic:** in round 2, the reviewer asked "What is the exact
structure of qttune_frame_t?" in its questions channel while filing a
stack-memory-use blocker. The model's epistemic state was correct —
uncertain — but the taxonomy discipline failed: hedged speculation was
promoted to a demonstrable-violation claim.

## Decision

Adjudication is implemented as deterministic guardrails over model
output, not prompt pleas. Failure classes are remediated per-class with
the narrowest mechanism that addresses the root cause:

1. **Hedge demotion** (class: speculative phrasing) — blockers whose
   text contains hedge language ("may", "might", "could", "appears to")
   are demoted to questions before judging. Regex guardrail
   (adjudication.demote_hedged_blockers), regression-tested against
   production-derived blocker texts — runnable with no LLM.

   Deliberate boundary: catches phrased-as-speculation only.
   Confidently stated assertions — including wrong ones — pass through.
   Verified experimentally: a reviewer confidently flagging a race
   condition documented in the code's own comment was correctly NOT
   demoted.

2. **Layer metadata injection** (class: layer misapplication) —
   file_metadata.py maps paths to QtTune layers (core/bridge/app);
   the transcript states which rules apply, pre-legitimizing
   bridge-layer Qt includes.

3. **Definition-context injection** (class: information deficit) —
   planned (v2). Inject struct definitions and repo-level context
   as ground truth. Not a filtering problem: no regex can fix a model
   confidently asserting facts it cannot see.

Design principles, in priority order: fail closed on unusable input;
derive verdicts from content arrays, never self-reported labels;
separate what the model KNOWS (questions channel) from what it CLAIMS
(blockers channel); measure, remediate, re-measure.

## Re-Measurement After v1 (2026-10-09)

Same diff, same models, same prompt version. Prediction recorded
before running: Qt-leakage gone, hedged stack-memory claims demoted,
hardcoded-8 catch retained.

| Class | Baseline | v1 Re-run | Result |
|---|---|---|---|
| Layer-rule misapplication | 7 | 0 | Eliminated |
| Hedge-speculation | 3 | 0 | Eliminated — notably, 0 demotions fired: the reviewer stopped hedging (taxonomy discipline at the source), the guardrail never triggered |
| Definition-context guessing | 3 | 1 | Persists — expected, not yet remediated |
| Confident-but-wrong assertions | 0 | 4 | NEW dominant class: thread-safety claims on m_currentFrameCount, which is GUI-thread-only by queued-connection construction |
| Real defect | 1 | 1 | Retained (hardcoded 8-byte buffer) |

Precision: 1/12 (~8%) → 1/6 (~17%). Blocker volume halved (12 → 6).

## Consequences

- The v1 remediations eliminated their target classes outright.
  What remains is almost entirely the information-deficit class:
  confident assertions from missing context. Hedge regex provably
  cannot address it; definition-context injection (v2) is the
  designated remedy. Prediction: the 4 thread-safety false positives
  require seeing the queued-connection call sites, which retrieval-
  based context injection can supply.
- An honest tension to keep visible: as FP rate drops, the reviewer's
  blockers become fewer and higher-precision — but single-run results
  remain anecdotes. The 1/12 → 1/6 delta is one run vs. one run;
  the class-level eliminations (7/7 and 3/3) are the stronger evidence.
- Cross-cutting limits identified: the reviewer still missed both
  real bugs found only by full-repo triage (drop-count starvation,
  staging-buffer last-write-wins). The diff-centric workflow itself
  caps recall, independent of precision. This motivates the repo
  context-pack work (see STATUS.md backlog).
- Golden suite now 10/10 (3 model fixtures + 7 deterministic guardrail
  units, production-derived texts). The deterministic subset is
  CI-suitable with no model serving.
  
  ## Erratum (2026-10-09)

Two defects found by external review (2026-10-09):

1. **Debate feedback loop was not wired.** `transcript_base` was frozen
   before the loop; the REVISE ADDRESSING feedback accumulated in the
   proposal variable but was never re-rendered into agent transcripts.
   Consequence: archived "3-round debates" were one exploratory sample
   (round 1) plus two constrained resamples — not adversarial
   iteration. Impact on recorded results: none on validity of the
   precision measurements (baseline and v1 re-measurement ran the same
   code, so they are internally consistent multi-sample comparisons;
   class-level eliminations stand), but records should be read as
   sampling measurements, not convergent debates. Fixed 2026-10-09:
   transcript re-rendered per round; PROMPT_VERSION bumped.
   Attribution note for future measurements: post-fix debates differ
   from archived ones in mechanism, not just remediation — per-class
   comparison remains the method.

2. **Bake-off summary conflated clean passes with bug hits** (second
   occurrence; prior fix never committed). ADR numbers unaffected —
   5/5 was read from individual result lines. Summary printer fixed;
   tp + fn invariant documented inline.
   
## Intermediate Measurement (2026-10-13) — Live Feedback Loop, No Context Injection

Not the context-pack measurement (that remains queued): this run
isolates a different variable. The 2026-10-09 records ran with the
dead feedback loop; this is the first run of the same diff and
proposal on the live loop (plus the 2026-10-10 hardening pass).

Prediction recorded before running: round 1 reproduces ~v1 volume
(5–7 blockers, 4 thread-safety FPs, decode defect retained), rounds
2–3 diverge, no agent failures, verdict MAX_ROUNDS_EXCEEDED.

Result: prediction MISSED on volume and placement.

| Class | v1 Re-run (014257) | Live loop (170208) |
|---|---|---|
| Round-1 blockers | 6 | 1 (m_currentFrameCount data race — confident-but-wrong) |
| Confident-but-wrong FPs | 4 | 1 (same m_currentFrameCount claim, consolidated) |
| Layer-rule FPs | 0 | 0 |
| Hedge demotions | 0 | 0 |
| decode_signal 8-byte defect | Caught as blocker | Raised as a ROUND-2 NIT ("verify data_length <= 8") |
| Verdict | MAX_ROUNDS_EXCEEDED | MAX_ROUNDS_EXCEEDED |

Round-1 precision: 0/1. Across all rounds: 0/5. Real defect visible
in-channel but mis-classified as an optional improvement.

Findings:

- Round-2/3 dynamics: the reviewer refined citations (splitting,
  then simplifying the race claim) rather than amplifying; the
  engineer held "approve" throughout. Feedback reached both agents
  (evidence: round-2 content responds to round-1 engineer concerns).
- Three stacked deltas make attribution impossible from one run:
  live loop, hardening (schema validation, layer note now "bridge"
  — v1 also had that), and model run-to-run variance. Laguna-xs-2.1
  is nondeterministic at temp 0.7; a 6→1 blocker drop is within
  plausible single-sample variance for this model.
- Defect drifting blocker→nit is a new failure mode worth watching:
  precision metrics that only count blockers will miss a defect the
  reviewer technically surfaced. Future measurements should scan all
  channels for known-defect mentions.

Record: `coach_artifacts/decision_debate_20261013_170208_71915a.json`,
fixture `docs/fixtures/qttune_bridge_refactor.diff` (hash f031d33a).

Implication: single-run blocker counts from this model cannot be
treated as stable measurements at current settings. The context-pack
measurement should run multiple times (or score a multi-run aggregate)
before claiming FP-class collapse.

## Fourth Measurement (Pending) — Context Pack Injection

**Design:** Same diff (`qttune_bridge_refactor.diff`), same proposal text,
same models (laguna-xs-2.1 + gemma4:12b), PROMPT_VERSION v5-context-pack,
**context pack now injected** (retrieved purposes, types, constants,
queued-connection call sites). N=3 runs, round-1 only, per-class
attribution. Control arms: v1 blind resample (014257), live-loop control
(170208).

**Indexed ground truth confirmed:** `app/qttunebridge.cpp` contains two
queued-connection call sites, both carrying `Qt::QueuedConnection`:
- Line 390: `invokeMethod(self, [...], Qt::QueuedConnection)` invoking
  `handleFrameInternal` — the receiver of m_currentFrameCount access
  flagged in the 170208 run as a "data race."

**Prediction (per-class rates, N=3):**

| Class | v1 (014257) | Live-loop control (170208) | Predicted (v5, N=3) |
|---|---|---|---|
| Thread-safety FPs (queued-conn class) | 4 | 1 | 0–2 (median 1) |
| Real defect (decode_signal 8-byte) | 1 (blocker) | 0 (drifted to nit) | 0–1 |
| Layer-rule FPs | 0 | 0 | 0 |
| Hedge FPs | 0 | 0 | 0 |
| Deletion-consistency FPs (new class) | 0 | 0 | 0–4 (emerging; pilot suggested 3) |

**Rationale for range, not point estimate:** the live-loop control
showed single-run variance of 6→1 blockers on near-identical inputs
(without retrieval). Even if retrieval supplies the queued-connection
ground truth that refutes the m_currentFrameCount claim, laguna-xs-2.1
at temp 0.7 may or may not draw on it within a single run. Three runs
estimate the per-class rate; median of 1 FP acknowledges variance while
predicting collapse of the *majority* of the 4-v1 FP class.

**Failure mode to watch:** decoder defect drifts blocker→question/nit
(as in 170208 round 2). Future precision metrics must scan all channels,
not just blockers.

**Confound noted:** index from current QtTune tree (40 files, j2534
changes added) while diff is older snapshot. Arguably realistic (reviews
run against current trees); if the 4 new files introduce new identifiers
the retrieval pulls, that's noise in the context but not bias in the
comparison (both arms measure retrieval's practical value).

**Record:** decision_record_[id].json for each run, `repo_context.json`
with callsites (idx_20261013_*).

## Results (2026-10-13, N=3)

Runs: `decision_debate_20261013_203802_276bd0` (run 1),
`decision_debate_20261013_204845_e4d1b3` (run 2),
`decision_debate_20261013_210548_6ce6c0` (run 3). Retrieval was
identical in all three runs (pack 1983/6000 chars, 14 entries, 2
queued-connection call sites, `error: null`) — deterministic across
runs. A pilot run (`ff958c`, wiring validation only) is committed as
unscored evidence and is excluded from these numbers.

| Class | Run 1 | Run 2 | Run 3 | Total | Prediction | Outcome |
|---|---|---|---|---|---|---|
| Round-1 blockers | 3 | 6 | 1 | 10 | — | — |
| Thread-safety FPs | 0 | 0 | 0 | 0 | 0–2 | **HIT — class collapsed, 3/3 runs** |
| Deletion-consistency FPs | 2 | 6 | 0 | 8 | 0–4 | **MISSED HIGH** |
| True positives | 1 | 0 | 1 | 2 | — | Best catches in project history |
| Hedge demotions | 0 | 0 | 1 | — | — | First firing since remediation |

Round-1 precision: **2/10 (20%)**; run-level 1/3, 0/6, 1/1. Run 2
ended `AGENT_FAILURE` at round 2 (num_ctx truncation); its round-1 arm
completed cleanly and is scored as pre-declared.

**True positives (both adjudicated against the diff's post-state and
QtTune real history):**

1. Run 1: the cumulative `m_currentFrameCount` gate drops every frame
   permanently after 10,000 total frames — and the diff deletes
   `StreamingContinuesPastTenThousandFrames`, the regression test
   guarding exactly this regression. Maintainer-confirmed as the
   historical freeze bug.
2. Run 3: data race on plain `int m_currentFrameCount` — read in
   `onFrame()` on the worker thread (backpressure check), written in
   `handleFrameInternal()` on the GUI thread; unsynchronized in the
   diff's post-state. The pilot additionally showed the claim
   returning as round-3 blockers after the live feedback loop carried
   the engineer's concern back to the reviewer.

**Fixture provenance (established by forensics, correcting an earlier
misreading):** the fixture is the reverse patch of merged QtTune
commit `e0c4c31`; its post-state is byte-identical to QtTune's
committed `8ffbf19` bridge state (blob `1c195f8`, verified via
`git log --all --find-object=1c195f8`). Both TPs are therefore bugs
that **actually shipped** and were later fixed in real history: the
freeze by `e0c4c31`'s in-flight gate plus the restored regression
test (documented in `d565764`), and the thread boundary by the
worker-path hardening in `b47687c`. The reviewer detected two real,
previously-shipped bugs from a diff alone.

**Negative findings (recorded, not yet remediated):**

- **Deletion-consistency class exceeded prediction** (8 total, 6/0/1
  by run — extreme variance): the reviewer fabricates surviving
  remnants of jointly removed code ("signalModel() still declared"),
  all false against the diff. Candidate remediation: ground removed
  symbols from the diff's minus side and require confirmation before
  assertion.
- **Hedge demotion fired once, on a hedged formulation of a TRUE
  thread-safety claim** (run 3, round 1). Hedged language does not
  imply incorrectness; strengthens the case for backlog #12.
- **num_ctx crowding:** the pack (~2k chars) plus feedback growth
  caused `done_reason=length` truncations in rounds 2+ (one
  AGENT_FAILURE). The retrieval budget competes with the debate
  loop's context growth; pack-from-rounds-2+ or a larger num_ctx is
  the trade space.
  *Correction (2026-10-22, code review 2026-10-21 finding 8):* the
  prompt sizes do not support this attribution. In run 2 the diff is
  26,695 of ~32,000 prompt chars (~83%); the pack is 2,023 and the
  reviewer system prompt 1,890, and the proposal grew from 66 to 1,371
  chars. Round 2's prompt was only ~4% larger than round 1's, which
  completed. Thinking-token output in a nearly full 16K window is the
  likelier driver, but no token counts were recorded, so it is
  unverified. Debates record per-attempt token telemetry from
  2026-10-22 on (STATUS backlog #4). The trade space is an output cap
  (`num_predict`) or a larger num_ctx; dropping the pack recovers
  little.
  *Telemetry follow-up (2026-10-22):* two live debates on the
  bridge-refactor fixture recorded per-attempt token counts. Both ran
  at v5.2-pack-sections with num_ctx 16384 and the 2,816-char pack.
  They are telemetry evidence only: no prediction was recorded and the
  blockers are unscored. Records: `decision_debate_20261022_134539_3026b2`
  (run A) and `decision_debate_20261022_140943_bbe168` (run B).

  | Reviewer | Prompt tokens | Output tokens, run A | Output tokens, run B |
  |---|---|---|---|
  | Round 1 | 9,397 | **6,987 (`length`)**, retry 493 | 1,119 |
  | Round 2 | ~9,820 | 1,891 | 4,460 |
  | Round 3 | ~10,150 | 1,124 | 1,946 |

  - **The one truncation was in round 1,** where there is no feedback
    yet: 9,397 + 6,987 = 16,384, at temperature 0.7. The retry at 0.05
    succeeded with 493 tokens, so the debate continued.
  - **The prompt is stable.** Feedback adds ~400 tokens per round. The
    pack is ~820 tokens (~3.4 chars per token).
  - **The output decides it.** Successful reviewer outputs ranged from
    493 to 4,460 tokens; the runaway reached at least 6,987.
  - **The token counts are trustworthy.** The retry reported the full
    9,412 prompt tokens, so prefix caching did not hide prompt tokens.
  - **The engineer peaked at 13,105** tokens in total.

  This confirms the correction above. The output, thinking included,
  fills the window; feedback and pack growth are not the cause.
  **Decision:** debates move to num_ctx 24576 (`config.NUM_CTX`), which
  roughly doubles the output headroom to ~15K tokens. An output cap
  alone would only make a runaway fail sooner, since it still yields no
  JSON. Limiting thinking (the model reports Ollama's `thinking`
  capability) changes reviewer behaviour and would need its own
  measurement. On the RTX 3060 (12 GB) the 20.7 GB model's GPU share
  drops from 48% to 46%. Expect slightly slower calls; the next live
  runs' `wall_s` will show by how much.
  *Second follow-up (2026-10-22, num_ctx 24576):* two more runs, same
  fixture, settings and caveats. Records:
  `decision_debate_20261022_143424_1b11cc` (run C) and
  `decision_debate_20261022_145342_743bc4` (run D).

  | Reviewer | Run C output tokens | Run D output tokens |
  |---|---|---|
  | Round 1 (temp 0.7) | 7,734 (171 s) | 1,506 |
  | Round 2 (temp 0.05) | **14,811 (`length`, 318 s)**, retry 444 | 10,097 (221 s) |
  | Round 3 (temp 0.05) | 2,134 | **14,501 (`length`, 310 s)**, retry 420 |

  - **24576 did not remove the failures.** Two of six first attempts
    ran away, each to exactly the new limit
    (9,765 + 14,811 = 10,075 + 14,501 = 24,576). At 16384 the rate was
    one of six.
  - **The larger window still helped.** Two replies finished at 7,734
    and 10,097 output tokens, which would have failed at 16384. With the
    same outputs, runs C and D would have lost four of six first
    attempts at 16384 instead of two.
  - **Runaways now cost about twice as long,** ~310 s against ~159 s,
    and they also occur at temperature 0.05.
  - **Every retry recovered quickly,** with 420–493 output tokens in
    10–13 s across all four runs. The "Invalid JSON" correction appears
    to cut the thinking short. So 3 of the 12 reviewer rounds were
    decided by a short, low-thinking reply. Treat those rounds as a
    different mode when scoring blockers.
  - **Thinking is on in JSON mode.** A JSON-mode probe returned a
    `thinking` field of ~3,700 chars, counted in `eval_count`. A reply
    forced to stop at 60 tokens came back with its partial thinking and
    empty content. That is the shape of the runaways: they fail as
    "not valid JSON" because the answer never starts.

  **Revised decision.** Keep 24576, because it rescues long replies
  that do finish. The rejection of an output cap above assumed
  runaways were long replies that would finish. They are not bounded
  by the window, so failing fast followed by the reliable retry may be
  the better trade. Before choosing, telemetry now keeps
  `thinking_chars` and `content_chars` for every attempt, plus the last
  400 chars of thinking and content for failed ones. The next runaway
  will show which case applies:
  - If the model is looping, cap output with `num_predict`.
  - If it is reasoning at length, measure Ollama's `think` control.

  *Third follow-up (2026-10-22, first runaway with diagnostics):* run E,
  `decision_debate_20261022_153943_7a4809`, same fixture and settings.
  - **The runaway was the engineer** (`gemma4:12b`), in round 2 at
    temperature 0.05. It produced 14,525 output tokens and 47,046 chars
    of thinking, and never started its reply (`content_chars` 0). Its
    retry finished in 2,124 tokens. Runaways therefore occur in both
    models.
  - **It was a loop.** The 400-char tail holds one full cycle and
    starts and ends on the same phrase:

    > *I'll flag it as a blocker.* / *Wait, I'll just follow the
    > persona.* / *Persona: Senior Engineer advocating for v0.2.0
    > goals. Goal: Shipping velocity. Action: Approve the roadmap
    > move.* / *Wait, I'll check the "Blocker" rule again.* / *If I
    > don't flag it, and it's a violation, I'm wrong.* / *I'll …*

    The engineer prompt pulls two ways. The persona says to argue for
    roadmap fit and leave implementation correctness to the reviewer.
    The rules say a demonstrable violation is a blocker. The model
    alternated between the two without converging.
  - **Across runs A–E** (34 attempts, 30 of them first attempts),
    finished replies had a median of 1,506 tokens for the reviewer and
    1,968 for the engineer. The longest were 10,097 and 5,596. All four
    runaways were first attempts, and all four retries recovered.

  **Decision:** cap output at `num_predict` 12,288 (`config.NUM_PREDICT`),
  per the rule recorded above. The cap is above every finished reply,
  and a runaway now stops ~15% sooner (12,288 against ~14,500 tokens). The reviewer's runaways
  happened before the diagnostic existed, so it is not yet known
  whether they loop too. Two follow-ups are filed: stop a loop early by
  streaming the reply (STATUS backlog #19), and resolve the engineer
  prompt's persona-versus-blocker conflict (#20).

  *Verification (2026-10-22, num_predict 12288):* runs F
  (`decision_debate_20261022_160429_15cc3f`) and G
  (`decision_debate_20261022_161800_5b3f1d`), same fixture and caveats.
  - **The cap works.** Run F had two runaways, both stopped at exactly
    12,288 output tokens, after 272 s and 186 s (runaways at 24576
    uncapped had taken ~310 s). Both retries recovered. Run G had none.
  - **The second engineer runaway was the same conflict** (run F,
    round 3): *"If I don't block a data race, I'm ignoring a safety
    violation. I'll put it in 'blockers'. Wait, if I block, I'm not
    advocating for 'Shipping Velocity'. … I will approve the intent but
    list the implementation issues as concerns."* Both engineer
    runaways are this loop.
  - **The reviewer runaway did not look like a loop** in its 400-char
    tail (run F, round 2, 48,034 chars of thinking): *"Now I have
    identified the blockers. Let me also check for any other potential
    issues. Looking at the code, I also notice that
    `m_currentFrameCount` is used in `clearFrames` …"* It reads as an
    open-ended search for more issues. A repeat cycle longer than 400
    chars cannot be ruled out.
  - **The reviewer's retry used no thinking at all** (267 output tokens,
    `thinking_chars` 0). The engineer's retry did think (8,470 chars).
    This confirms that a retried reviewer round is a different mode.
  - **The cap's margin is thin.** Run G's round-1 reviewer reply
    finished at 9,971 tokens; the longest finished reply is still
    10,097, ~18% under the cap. Uncapped reviewer runaways reached at
    least 14,500, so the cap sits in the gap between them.
  - **Totals for runs A–G:** 6 runaways in 42 first attempts (4
    reviewer, 2 engineer), all on a first attempt, and all 6 retries
    recovered.

**Re-adjudication flag (retroactive):** the v1 re-measurement's
dominant residual class — thread-safety claims on
`m_currentFrameCount`, refuted as "GUI-thread-only by
queued-connection construction" — is **invalidated by the forensics
above**: in the fixture's post-state the variable IS read on the
worker thread. Some of the four v1 "confident-but-wrong" FPs and the
170208 control's single blocker are likely true positives, mislabeled
because the triage refutation was drawn from maintained QtTune rather
than the diff's post-state. Those runs warrant re-triage against
their blocker texts before their historical FP counts stand. This
measurement's numbers are unaffected — scored against the diff text.

**Interpretation:** the context pack did what it was designed to do —
eliminated the targeted information-deficit class in 3/3 runs, with
the residual concern correctly filed as questions — and enabled the
best catches in the project's history. But total FP volume did not
fall; it migrated to a new hallucination class. The tribunal now
knows what the code contains; it still cannot reliably reason about
what a diff removes. Per the standing loop, that is the next class to
remediate and re-measure.
## Fifth Measurement (Pending) — Context-Pack Ablation

*Prediction recorded 2026-10-22, before any arm was scored.*

**Question** (code review 2026-10-21, finding 1): does the context pack
cause the deletion-consistency class? The pack is built from the
current QtTune tree, but the fixture removes code that tree still has,
and the transcript labels the pack ground truth that wins over the
diff. The fourth measurement's design noted this confound and judged it
noise rather than bias; this measurement tests that judgment.

**Arms** (same fixture, proposal text and models; PROMPT_VERSION
v5.2-pack-sections; prompt fingerprint `56b27d0a29161c81` for pack
runs):

1. **Stale pack (records exist).** The six scorable 2026-10-22
   telemetry runs: bbe168 (num_ctx 16384), 1b11cc, 743bc4, 7a4809
   (24576), 15cc3f, 5b3f1d (24576, num_predict 12288). All saw the same
   2,816-char pack (sha256 `e04d13e9…`). 3026b2 is excluded because its
   round-1 reviewer output came from a retry. The settings differ only
   in output headroom; every scored first attempt ended normally
   (`done_reason` stop).
2. **No pack (to run, N=3).** Retrieval disabled, current settings.
3. **Post-state pack (to run, N=3).** Index built from QtTune `8ffbf19`,
   the diff's post-state, current settings.

**Disclosure for arm 1:** these records predate this prediction. Seen
so far: telemetry, round-1 blocker counts for runs 3026b2 and bbe168,
and debate-level blocker totals. Not seen: the text of any round-1
blocker.

**Unit:** round-1 reviewer blockers from first attempts, as stored
(after hedge demotion).

**Frozen symbol set P** (pack-asserted, removed by the diff): every
identifier that appears on the diff's minus side, does not appear on
its plus side, appears in the pack text, and has zero hits in the
post-state tree (`git grep -w` at `8ffbf19`). That is
`SignalListModel`, `MaxInFlightFrames` and `m_inFlightFrames`.
`fetch_sub` also qualifies but is excluded as a generic `std::atomic`
method. `QttuneSignalDef` and `QttuneSignalSet` survive in the
post-state and are not in P.

**Metrics:**

- **M1 (mechanical):** blockers whose text contains a P symbol (whole
  word, case-sensitive).
- **M2 (adjudicated; deletion-consistency FP):** blockers asserting
  that something the diff removes still survives (is still declared,
  referenced, used, tested or exposed) where the post-state shows it
  does not. Each claimed survivor is checked with `git show` /
  `git grep` at `8ffbf19`. M2 is split into **M2-P** (cites a P symbol)
  and **M2-other**.
- **Scorer check, not a measurement:** M1 applied to the four v5
  records (ff958c, 276bd0, e4d1b3, 6ce6c0), compared with the review's
  table (3/4, 2/3, 5/6, 0/1).

**Prediction:**

| Metric (round 1, first attempts) | Stale pack (6 runs) | No pack (N=3) | Post-state pack (N=3) |
|---|---|---|---|
| M2, total | 6–18 (mean 1–3 per run) | 0–2 | 0–2 |
| Runs with M2 ≥ 1 | ≥ 4 of 6 | ≤ 1 of 3 | ≤ 1 of 3 |
| M2-P as a share of M2 | ≥ 50% | — | — |

**Basis:** the three scored v5 runs had 2, 6 and 0 deletion-consistency
FPs (mean 2.7), and the review found most of their round-1 blockers
citing a P symbol. Runs without a pack (014257, 170208) had none. The
v5.2 pack asserts the same three symbols, now with fuller declarations.

**Decision rule** (on per-run M2 means):

- **Pack-driven:** no-pack mean ≤ stale-pack mean − 1.0, and post-state
  mean ≤ no-pack mean + 0.7. Remediate in retrieval (finding 1:
  post-state index, flag removed symbols, invert the precedence
  wording). Defer backlog #15 until re-measured.
- **Intrinsic:** no-pack mean ≥ 0.7 × stale-pack mean. The class does
  not need the pack, so #15 proceeds and the retrieval fixes are
  hygiene.
- **Otherwise inconclusive:** add N=3 to each new arm before deciding.

**Power caveat:** with per-run counts as variable as 6/0/1, N=3 per
arm detects only a large effect. A null result here is weak evidence.

### Arm 1 results (scored 2026-10-22)

| Metric | Predicted | Observed | Outcome |
|---|---|---|---|
| M2, total | 6–18 | **3** (2 without the borderline case) | **MISSED LOW** |
| Runs with M2 ≥ 1 | ≥ 4 of 6 | 2 of 6 | **MISSED** |
| M2-P as a share of M2 | ≥ 50% | 3 of 3 | HIT |
| M1 (no prediction) | — | 4 of 19 blockers | — |

| Run | Round-1 blockers | M1 | M2 | Composition |
|---|---|---|---|---|
| bbe168 | 5 | 2 | 2 | 2 deletion-consistency, 3 feature-removal objections |
| 1b11cc | 5 | 1 | 0 | 5 feature-removal objections |
| 743bc4 | 3 | 1 | 1 | 1 deletion-consistency, 2 feature-removal objections |
| 7a4809 | 2 | 0 | 0 | 2 × the `m_currentFrameCount` race |
| 15cc3f | 2 | 0 | 0 | the race; `m_droppedFrames` ordering (unadjudicated) |
| 5b3f1d | 2 | 0 | 0 | the race; 8-byte decode in removed code |

**The three M2 blockers, checked against the post-state (`8ffbf19`):**

1. **bbe168 #5** — *"Line 390 in app/qttunebridge.cpp: The comment
   references m_inFlightFrames.fetch_sub but that atomic counter and
   MaxInFlightFrames constant were removed from the header, creating a
   dangling reference."* The post-state file has 269 lines, and
   `m_inFlightFrames` has no hits anywhere in the tree. Line 390 exists
   only in the indexed tree (`6b58c3a`), where it is the call site the
   pack shows: `[app/qttunebridge.cpp:390] QMetaObject::invokeMethod(…
   calls: m_inFlightFrames.fetch_sub, handleFrameInternal …)`. The
   citation is copied from the pack.
2. **743bc4 #2** — *"The QML Main.qml previously bound to
   QtTune.signalModel … with SignalListModel gone, this property no
   longer exists, creating a broken QML binding."* Post-state `Main.qml`
   contains no `signal` reference, and `signalModel` has no hits.
3. **bbe168 #1 (borderline)** — *"SignalListModel class definition was
   removed from header but referenced in QML."* No post-state QML
   references `SignalListModel` or `signalModel`. Borderline because the
   same blocker also notes that `LiveViewPage.qml` was deleted.

**Other observations:**

- **The class was far rarer than in v5:** 0.5 per run against 2.7. A
  newer composition dominates instead. 10 of 19 blockers object that
  the diff removes the LiveView feature, signal decoding, batching or
  tests, without claiming anything survives. 4 report the
  `m_currentFrameCount` race, the fourth measurement's run-3 TP; they
  appear in all three of the later runs. With N=6 the cause of the
  shift cannot be separated from sampling variance (v5 itself was
  2/6/0).
- **New confound: the proposal contradicts the diff.** The proposal
  text used for every bridge-fixture run since the 2026-10-07 baseline,
  *"Review: coalesced signal updates with LiveView Page v0.3.0 phase
  2"*, is the subject line of `e0c4c31`. That commit **adds**
  `LiveViewPage.qml` (+64 lines). The fixture is its reverse patch and
  **deletes** it. So the debates are told they are reviewing the
  feature's arrival while the diff removes it. The feature-removal
  objections are a reasonable reaction to that, and the proposal is a
  second source, besides the pack, asserting that the removed code
  exists. The text is constant across all arms, so it does not bias
  this ablation. The no-pack runs (014257, 170208) used it too and had
  no deletion-consistency FPs, which points at the pack rather than the
  proposal.
- **Scorer check:** M1 on the v5 records gives 1/4, 2/3, 4/6 and 0/1,
  against the review's 3/4, 2/3, 5/6 and 0/1. Two rows match. The v5
  records do not store their pack text, so the review's symbol sets
  for them cannot be reconstructed. Some v5 deletion FPs cite removed
  symbols outside P (`signalModel`, `forceFrameCountForTesting`).

**Consequence for the decision rule:** with a stale-pack mean of 0.5,
the rule as written cannot return "pack-driven", because that needs a
no-pack mean of −0.5 or less. Arms 2 and 3 at N=3 can only return
"intrinsic" (two or more M2 across the three no-pack runs) or
"inconclusive". Any change to the rule or to N must be recorded here
as an amendment before those arms run.

### Amendment (2026-10-22): arms 2 and 3 not run; retrieval fixed instead

**Decision:** skip the no-pack and post-state arms and fix retrieval
directly. With arm 1 at 0.5 per run, the pre-registered rule could no
longer return "pack-driven". One arm-1 blocker already shows the stale
pack injecting a false fact (the line-390 citation). And finding 1's
retrieval changes are correct whatever the ablation would show: a
snapshot of another tree should never overrule the diff. Whether the
class is pack-driven or intrinsic stays unanswered.

**What changed (PROMPT_VERSION v6-diff-authoritative, pack format
f3-diff-authoritative):**

- **Precedence inverted.** The template calls the pack a snapshot of
  the indexed tree that may not match the code before or after the
  diff, says the diff is authoritative for everything it touches, and
  calls purposes machine-written summaries. The pack header reads
  "INDEXED SNAPSHOT"; nothing says "ground truth" any more.
- **Removed entries omitted.** An identifier counts as removed when it
  appears on the diff's removed lines and on no added line, unchanged
  context line or hunk header. Constants and types defined in a
  modified file under a removed name, and call sites in a modified file
  whose snippet uses one, are left out and listed by name only under an
  OMITTED section. A purpose that mentions one is annotated
  `[only on the diff's removed lines: …]`. Entries outside the modified
  files are never touched, since the diff cannot show whether they
  survive.
- **Index aligned with the diff's base.** The committed index is
  rebuilt from QtTune `e0c4c31`, the fixture's base: every old-side blob
  in the fixture matches it. The index now records `source_commit` and
  `source_dirty`, and decision records carry the commit as
  `repo_context_pack.index_commit`.

**Next measurement:** a v6 baseline on the fixture, prediction first.
The deletion-consistency rate in arm 1 (0.5 per run) is too low to show
a reduction at small N, so the comparison should cover round-1 blocker
composition and precision as well, scored first-attempt only. The
proposal-text mismatch (STATUS #21) is still present and still
constant.

## Convergence Rule j2 (2026-10-22)

**Decision:** a round converges once neither derived verdict is
`reject`. Both `approve` gives `APPROVED_FOR_MERGE`; any open question
or concern gives `APPROVED_WITH_OPEN_QUESTIONS`. Rule j1 also required
the engineer's verdict to be `approve`, meaning zero concerns and
questions. The engineer returned concerns in every completed engineer
round on record, so no debate could converge (STATUS backlog #2,
minimal option). The rule is `adjudication.convergence_verdict`, and
records stamp it as `metadata.judge_version` because it changes
verdicts and round counts without touching a prompt.

**Replay over the 16 archived records** (derived verdicts recomputed
from the stored, post-demotion outputs): only header review 194320
changes. Its first round had open items but no blockers on either
side, so it would converge in round 1 as
`APPROVED_WITH_OPEN_QUESTIONS` instead of ending at max rounds. The
other 15 have reviewer blockers in every round and are unaffected.

**Effect on measurements:** none. Measurements score round-1 reviewer
output, which no judge rule can change.
