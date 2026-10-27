# ADR-0002: Rule-Based Adjudication and False-Positive Remediation

Date: 2026-10-13
Status: Accepted. A running log: every judge and prompt change measured
since 2026-10-07, newest last.

Supersedes the adjudication portions of ADR-0001.

## Index

Every section of this log, oldest first. Each measurement holds its
prediction and ship rule as written before its first sample, then its
results; changes made after seeing data are dated amendments.

| Section | Date | Change | Outcome |
|---|---|---|---|
| [Blocker Triage](#blocker-triage-original-run-2026-10-07) | 2026-10-07 | First real diff, one debate | 2 of 12 blockers valid (after the re-triage below) |
| [Decision](#decision) | 2026-10-07 | v1 guardrails: derived verdicts, hedge demotion, layer notes | Adopted |
| [Re-Measurement After v1](#re-measurement-after-v1-2026-10-09) | 2026-10-09 | v1 on the same diff | 4 of 6 valid; layer-rule false positives gone |
| [Intermediate Measurement: Live Feedback Loop, No Context Injection](#intermediate-measurement-2026-10-13--live-feedback-loop-no-context-injection) | 2026-10-13 | Live feedback loop as a control | Feedback reintroduced false blockers in round 3, so later measurements score round 1 |
| [Fourth Measurement: Context Pack Injection](#fourth-measurement--context-pack-injection) | 2026-10-13 | Context pack from a repo index (N=3) | 3 of 10 valid; the race found once, the first gate blockers |
| [Fifth Measurement: Context-Pack Ablation](#fifth-measurement--context-pack-ablation) | 2026-10-22 | Context-pack ablation | Claims of surviving removed code cite the stale pack; led to v6 |
| [Convergence Rule j2](#convergence-rule-j2-2026-10-22) | 2026-10-22 | A blocker-free round converges | Shipped (judge j2) |
| [Sixth Measurement: v6 Baseline](#sixth-measurement--v6-baseline) | 2026-10-22 | v6: diff authoritative over the pack | 42% valid; the surviving-code class persists without the pack |
| [Seventh Measurement: Survival-Claim Check](#seventh-measurement--survival-claim-check-backlog-15) | 2026-10-22 | A survival-claim check | Parked |
| [Eighth Measurement: Arm H: No Hedging Ban](#eighth-measurement--arm-h-no-hedging-ban) | 2026-10-22 | Arm H: no ban on hedged blockers | Not supported: the reviewer did not hedge more |
| [Ninth Measurement: Arm G: Evidence-Quoted Blockers](#ninth-measurement--arm-g-evidence-quoted-blockers) | 2026-10-22 | Arm G: quotes from either side | Not shipped: false claims moved to removed lines |
| [Tenth Measurement: Arm G3: Post-Change Quotes](#tenth-measurement--arm-g3-post-change-quotes) | 2026-10-22 | Arm G3: post-change quotes only | Shipped (v9, j4): 94% valid |
| [Evidence Reader j5](#evidence-reader-j5-2026-10-22) | 2026-10-22 | One shared diff reader | No recorded result changed |
| [Hedge Check j6](#hedge-check-j6-2026-10-22) | 2026-10-22 | The hedge check reads the claim, not the quote | No recorded result changed |
| [Eleventh Measurement: Transcript Protocol v10](#eleventh-measurement--transcript-protocol-v10-backlog-11) | 2026-10-22 | Transcript protocol v10 | The fence shipped (v10.1); the critiques section did not |
| [Input Checks j7](#input-checks-j7-2026-10-23) | 2026-10-23 | Empty and oversized input refused before any call | Shipped (judge j7) |
| [Golden Suite Routing](#golden-suite-routing-2026-10-23-backlog-14) | 2026-10-23 | Golden fixtures through the real round-1 path | 10/10, as predicted |
| [Unknown-Layer Note v10.2](#unknown-layer-note-v102-2026-10-23) | 2026-10-23 | A note for input with no path | Shipped (v10.2) |
| [Re-Triage of the Early Runs](#re-triage-of-the-early-runs-2026-10-23-backlog-17) | 2026-10-23 | Early runs re-labeled against the diff's post-state | The 'false positives' were the real race |
| [Twelfth Measurement: Feedback Section v11](#twelfth-measurement--feedback-section-v11-backlog-11) | 2026-10-23 | Feedback section v11 | Shipped (v11.1) |
| [Thirteenth Measurement: Offline Replay of Judge Variants](#thirteenth-measurement--offline-replay-of-judge-variants) | 2026-10-23 | Offline replay of judge variants | Linkage and voting become corpus candidates |
| [Fourteenth Measurement: Corpus Baseline](#fourteenth-measurement--corpus-baseline-backlog-7) | 2026-10-23 | Corpus of seven real diffs, baseline | 57% valid, mean recall 0.46 |
| [Fifteenth Measurement: Corpus Replay and a Removed-Line Exception](#fifteenth-measurement--corpus-replay-and-a-removed-line-exception) | 2026-10-23 | Judge variants replayed on the corpus | Linkage passes; voting and removed-line exceptions fail |
| [Sixteenth Measurement: Fresh Corpus Sample](#sixteenth-measurement--fresh-corpus-sample) | 2026-10-23 | A fresh corpus sample, labeled before replay | Linkage confirmed |
| [Claim–Quote Linkage j8](#claimquote-linkage-j8-2026-10-23) | 2026-10-23 | Claim–quote linkage | Shipped (judge j8) |
| [Seventeenth Measurement: Repair Pass for Quote Failures](#seventeenth-measurement--repair-pass-for-quote-failures) | 2026-10-24 | A repair call for demoted quotes | Not shipped: recall +0.009 |
| [Eighteenth Measurement: Repair Successor: Ceiling Check and Pilot](#eighteenth-measurement--repair-successor-ceiling-check-and-pilot) | 2026-10-24 | A dedicated repair prompt: ceiling and pilots | Closed at the pilot |
| [Nineteenth Measurement: Removal-Caused Defects Quoted in Round 1](#nineteenth-measurement--removal-caused-defects-quoted-in-round-1) | 2026-10-25 | A round-1 quote rule for removals | Not shipped: recall +0.05 of +0.10; cross-hunk linkage closed by its ceiling |
| [Twentieth Measurement: Field Writers in the Context Pack](#twentieth-measurement--field-writers-in-the-context-pack) | 2026-10-26 | Field definitions and writers in the pack | Not shipped: target false positives rose |
| [Twenty-First Measurement: Per-File Layer Notes](#twenty-first-measurement--per-file-layer-notes) | 2026-10-26 | Per-file layer notes | Not shipped: bridge false positives rose |
| [Runaway Diagnostic: Do Runaways Repeat?](#runaway-diagnostic--do-runaways-repeat) | 2026-10-26 | Whole thinking of runaways and long replies (backlog #19) | Closed: no repetition threshold separates runaways from long replies; an early retry cuts valid findings |
| [Twenty-Second Measurement: Reviewer Model Bake-Off](#twenty-second-measurement--reviewer-model-bake-off) | 2026-10-26 | Two local reviewer models against laguna on the corpus | Closed: `qwen3-coder:30b` mean recall 0.09 against 0.42; nemotron dropped at Stage 0 (runs to the cap); laguna stays |
| [Twenty-Third Measurement: Engineer Model Bake-Off](#twenty-third-measurement--engineer-model-bake-off) | 2026-10-26 | `gpt-oss:20b` against gemma as the engineer | Not shipped: recall in any item +0.23, but 0.24 false blockers per review (bar 0.10) |

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

*Re-triaged 2026-10-23 against the post-state (see "Re-Triage of the
Early Runs"): 2 of 12 valid, both the race (R1 #4 and #5, counted here as
layer-rule). The real defect is in code the diff removes, and so is the
staging buffer.*

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

*Re-triaged 2026-10-23: 2/12 → 4/6. The four confident-but-wrong
blockers are the race, and the real defect is in removed code (see
"Re-Triage of the Early Runs").*

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

*Re-triaged 2026-10-23: 1/1 and 5/5, all the race. The decode defect
this row tracked is in removed code (see "Re-Triage of the Early
Runs").*

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

## Fourth Measurement — Context Pack Injection

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

*Re-triaged 2026-10-23: 3/10. 276bd0 #2 is the in-flight gate, and #1 a
removal objection. The thread-safety class held no false positives to
remove (see "Re-Triage of the Early Runs").*

**True positives (both adjudicated against the diff's post-state and
QtTune real history):**

1. Run 1: the cumulative `m_currentFrameCount` gate drops every frame
   permanently after 10,000 total frames — and the diff deletes
   `StreamingContinuesPastTenThousandFrames`, the regression test
   guarding exactly this regression. Confirmed against QtTune's
   history as the freeze bug.
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

*Executed 2026-10-23 (backlog #17): all four v1 blockers and every
control blocker are the race, so the interpretation below does not hold
for the thread-safety class. This measurement's own labels changed too,
because the gate became a valid class later (see "Re-Triage of the Early
Runs").*

**Interpretation:** the context pack did what it was designed to do —
eliminated the targeted information-deficit class in 3/3 runs, with
the residual concern correctly filed as questions — and enabled the
best catches in the project's history. But total FP volume did not
fall; it migrated to a new hallucination class. The tribunal now
knows what the code contains; it still cannot reliably reason about
what a diff removes. Per the standing loop, that is the next class to
remediate and re-measure.
## Fifth Measurement — Context-Pack Ablation

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

## Sixth Measurement — v6 Baseline

*Prediction recorded 2026-10-22, before any v6 sample was run. No v6
blocker has been seen.*

**Question:** with the diff authoritative over the pack (v6), does the
deletion-consistency class persist? The answer decides backlog #15.

**Design:**

- **Arm:** v6. PROMPT_VERSION `v6-diff-authoritative`, pack format
  `f3-diff-authoritative`, prompt fingerprint `64bacb21aa6fb8b1`. The
  2,562-char pack (sha256 `dfac132e…`) comes from the index of QtTune
  `e0c4c31`, the fixture's base.
- **Inputs and settings:** the same fixture, models and proposal text
  as every bridge run. The text still contradicts the diff (STATUS #21);
  a matching-proposal arm was considered and not run. num_ctx 24576,
  num_predict 12288, first attempts at temperature 0.7.
- **Comparison:** fifth measurement arm 1 (v5.2, six runs, 19 blockers).
  Per run, that arm averaged 3.17 blockers, M1 0.67 and M2 0.5 (0.33
  without the borderline case). It also had 1.67 feature-removal
  objections and 0.67 race blockers (in 3 of 6 runs) per run.
- **What v6 changes:** v6 differs from arm 1 in three ways at once: the
  precedence wording, the omitted entries and the index base. This
  measures v6 as a unit and cannot attribute an effect to any one of
  them. The engineer prompt conflict (#20) is deferred, and round-1
  scoring never reads the engineer.
- **Sampling:** 10 samples from the round-1 measurement mode
  (`python -m eval_harness.round1 run`). Each sample is the request a
  debate's first reviewer call sends; a test pins the equality, and the
  records share the debate's fingerprint. Arm 1's samples came from full
  debates, but a debate's round-1 reviewer never sees the engineer, so
  the sampled outputs are comparable. Samples whose round-1 reply came
  from a retry, or that failed, are excluded and reported. Excluded
  samples are not replaced.
- **Unit:** the same as the fifth measurement: round-1 reviewer
  blockers from first attempts, as stored after hedge demotion.
- **Frozen P:** unchanged: `SignalListModel`, `MaxInFlightFrames`,
  `m_inFlightFrames`. The v6 pack still names all three, but only as
  removed (annotated purposes, the OMITTED list), never as present.

**Metrics and scoring:**

- **M1:** scripted, by `eval_harness.round1 score`.
- **M2:** adjudicated as before, against `8ffbf19`. The scorer's
  candidates must include every confirmed M2; arm 1 had 3 of 3 among
  its 10 candidates.
- **Composition:** each blocker is one of deletion-consistency (M2),
  feature-removal objection, the `m_currentFrameCount` race, or other.
  Other blockers are adjudicated one by one.

**Prediction** (scored runs; totals assume about 9 of 10 are scored):

| Metric | Arm 1 (v5.2, 6 runs) | Predicted v6 |
|---|---|---|
| M2, confirmed | 3 (0.5 per run) | 0–2 (≤ 0.2 per run) |
| M2 citing a P symbol | 3 | 0–1 |
| M1 | 4 (0.67 per run) | 1–6 (0.1–0.6 per run) |
| Blockers per run | 3.17 | 2–4 |
| Feature-removal objections, share of blockers | 10 of 19 | 35–65% |
| Runs with the race blocker | 3 of 6 | 3–7 of the scored runs |
| Samples excluded (retry or failure) | 1 of 7 | 0–3 of 10 |

**Basis:**

- **M2 should fall.** All three arm-1 M2 cited a P symbol that the stale
  pack showed as present, and one copied a line number from the pack. v6
  shows those symbols only as removed.
- **M2 may not reach zero.** Both the diff and the proposal still name
  the removed code, and the proposal says the feature is being added.
- **M1 falls less than M2.** Feature-removal objections name
  `SignalListModel` too (arm 1: 1b11cc #3).
- **Removal objections still dominate,** because the proposal is
  unchanged.
- **The race is untouched by v6.** It lives in `m_currentFrameCount`,
  which appears on both sides of the diff.

**Decision rule** (on confirmed M2 per scored run):

- **≤ 0.2: handled by v6.** #15 stays filed but deferred; next is #21.
- **≥ 0.4: persists.** The class survives without the pack asserting
  the symbols, so #15 proceeds.
- **Between:** add 5 samples and apply the same thresholds to all of
  them. If the result is still between, defer #15 and record it as
  unresolved.

**Power caveat:** arm 1's rate of 0.5 per run predicts about 5 M2 in 10
runs if v6 changed nothing. A Poisson count with mean 5 is ≤ 2 about
12% of the time. So "handled" is moderate evidence, not proof. Rates on
this fixture have also drifted widely: 2.7 per run at v5, 0.5 at v5.2.

### Results (scored 2026-10-22)

**Samples:** `coach_artifacts/measurement_round1_20261022_*.json`, from
205145_5d2fc3 to 210647_dc4008.
- All 10 replies came on the first attempt and ended normally
  (`done_reason` stop), so all 10 are scored.
- Every sample carries fingerprint `64bacb21aa6fb8b1` and pack
  `dfac132e…`. One hedge demotion fired (8e3c25).
- No reviewer reply ran away. Collecting all 10 took 16.4 minutes, or
  0.6–3.4 minutes per sample.

| Metric | Predicted | Observed | Outcome |
|---|---|---|---|
| M2, confirmed | 0–2 (≤ 0.2 per run) | **5 (0.5 per run)**, in 3 of 10 runs | **MISSED HIGH** |
| M2 citing a P symbol | 0–1 | 2 | **MISSED HIGH** |
| M1 | 1–6 | **10** | **MISSED HIGH** |
| Blockers per run | 2–4 | 2.6 (26 in all) | HIT |
| Feature-removal objections, share | 35–65% | 13 of 26 (50%) | HIT |
| Runs with the race blocker | 3–7 | 5 of 10 (7 blockers) | HIT |
| Samples excluded | 0–3 | 0 | HIT |

**Decision rule:** 0.5 confirmed M2 per run is ≥ 0.4, so the class
**persists** and #15 proceeds. The outcome holds under either
borderline call:
- Dropping the vaguest M2 (81a8dc #2) leaves 0.4.
- Adding the borderline non-M2 (a18d4b #2) gives 0.6.

**Composition:**

| Run | Blockers | M1 | M2 | Composition |
|---|---|---|---|---|
| 5d2fc3 | 2 | 1 | 0 | the race; in-flight gate |
| 8e3c25 | 4 | 1 | 1 | 1 deletion-consistency, 3 removal objections |
| ae1a96 | 2 | 0 | 0 | 2 × the race |
| fe4eea | 3 | 1 | 0 | 3 removal objections |
| a18d4b | 2 | 1 | 0 | the race; removal objection (borderline) |
| fcb3ac | 1 | 0 | 0 | the race |
| 81a8dc | 4 | 2 | 3 | 3 deletion-consistency; 8-byte decode in removed code |
| 6f29d3 | 3 | 2 | 0 | 2 × in-flight gate; removal objection |
| 07bb6b | 3 | 2 | 1 | in-flight gate; removal objection; 1 deletion-consistency |
| dc4008 | 2 | 0 | 0 | 2 × the race |

**The five M2 blockers, checked against `8ffbf19`:**

- **Four claim that `Main.qml` still references `QtTune.signalModel`:**
  8e3c25 #1, 81a8dc #1 and #4, and 07bb6b #3. `signalModel` has no hits
  in the post-state.
  - **`Main.qml` never referenced it, even before the diff.** The only
    `QtTune.signalModel` uses in the fixture are on the removed lines of
    `LiveViewPage.qml`, which the diff deletes. The pre-state `Main.qml`
    (`e0c4c31`) mentions `signalBatchCount` and `LiveViewPage {}`, not
    `signalModel`.
  - So the reviewer moves a reference from the deleted file onto the
    surviving one.
  - **The pack does not mention `signalModel` at all.**
- **81a8dc #2** says the deletion "leaves QML imports and references to
  removed components unresolved". `LiveViewPage` has no hits in the
  post-state. This is the vaguest of the five.
- **Not counted:** a18d4b #2 says the removal "breaks the QML binding
  contract even though LiveViewPage is deleted". It asserts no
  surviving reference.

**Removal objections whose cited comment does survive:** 8e3c25 #2 and
#4, and fe4eea #3, cite the post-state comments "sync the drop counter"
and `// TODO change to coalesce for v0.3 and real data`.
`app/qttunebridge.cpp` at `8ffbf19` has both, at lines 224 and 228.
These blockers are removal objections, not M2.

**What changed and what did not:**

- **The class kept its rate but changed its source.**
  - All three arm-1 M2 cited a P symbol that the stale pack showed as
    present.
  - At v6, four of five cite `signalModel`, which no pack has ever
    contained. The class does not need the pack to assert a symbol. So
    the fifth measurement's open question, whether the class is
    pack-driven or intrinsic, now leans intrinsic.
  - This is not a clean ablation: the v6 pack still names
    `SignalListModel` and the OMITTED entries.
- **M1 no longer tracks false positives.**
  - In arm 1, 3 of the 4 M1 blockers were M2.
  - At v6, 2 of the 10 are M2, 4 are in-flight-gate blockers (below)
    and 4 are removal objections.
  - M1 rose because removed symbols are now cited for valid reasons.
- **A new, valid sub-class: the in-flight gate.**
  - Four blockers in three runs (5d2fc3 #2, 6f29d3 #1 and #2, 07bb6b
    #1) object that the diff removes the `m_inFlightFrames` /
    `MaxInFlightFrames` gate. They say the remaining
    `m_currentFrameCount >= MaxFrames` check does not bound the queued
    backlog.
  - That is true of the post-state. `e0c4c31`, which the fixture
    reverts, describes its fix as "gate bounds in-flight queue depth
    (MaxInFlight), not cumulative frame count". The pre-state comment
    reads "bound the QUEUED backlog, not the lifetime count".
  - None of the four names the worse consequence, the permanent drop
    after 10,000 frames (the fourth measurement's run-1 TP), and one
    calls the remaining check "model capacity".
  - They are counted under removal objections, per the arm-1
    definition (objects to a removal without claiming survival). Arm 1
    had no such blocker. Whether the OMITTED list drew attention to the
    gate cannot be told from N=10.
- **The race held:** 7 blockers in 5 of 10 runs, against 4 in 3 of 6.
- **Implication for #15:**
  - A check that demotes every blocker citing a removed identifier
    would be wrong. Of the 16 scorer candidates, 5 are M2, 4 are the
    valid gate blockers and 7 are removal objections.
  - The check has to find a claim of survival ("still references",
    "remains", "dangling") about an identifier that only the removed
    lines contain. Citing a removed identifier is not enough.
  - The four `signalModel` cases also show where it must look: the
    claimed survivor sits in a file the diff touches but that never
    contained the name.
- **Scorer check:** all 5 confirmed M2 were among the 16 candidates.

## Seventh Measurement — Survival-Claim Check (backlog #15)

*Design and prediction recorded 2026-10-22, before the rule ran on
any held-out blocker. Draft for review: nothing is implemented yet.*

*Amendment (2026-10-22): parked before any held-out scoring.*
- **Why:** this regex checks a blocker's wording after the fact, as
  hedge demotion does. The v6 deletion FPs look like misreadings that a
  check on the evidence would catch however confident they sound.
- **Chosen instead, one variable at a time:**
  - the eighth measurement, H, drops the prompt's hedging ban;
  - the ninth, G, makes each blocker quote verifiable evidence.
- **Kept as a fallback if G fails.** The held-out sets A and B are
  still unread, so this design can be scored later as written.
  *(2026-10-23: no longer so. Backlog #17's re-triage read A's and B's
  blocker texts; see "Re-Triage of the Early Runs". The rule stays
  frozen.)*

**Problem:** the sixth measurement found deletion-consistency FPs at
0.5 per run without the pack asserting the symbols. A blocker of this
class claims that something only the diff's removed lines contain still
exists ("Main.qml still references `QtTune.signalModel`"). The diff is
enough to show the claim is unsupported.

**Rule (frozen; becomes judge `j3-survival-claims` if shipped):**

- **Removed-only identifiers:** the code-like identifiers
  (`_code_like`) in `_removed_identifiers(diff)`. These appear on the
  diff's removed lines and on no added, context or hunk-header line.
  Debate computes the set once and passes it in, so adjudication.py
  stays pure.
- **Sentences:** each blocker is split into sentences after `.`, `;`,
  `!`, `?` and at ` - `.
- **Fires when one sentence has either of these:**
  - **STILL:** a match of
    `\bstill\s+(?:\w+\s+){0,2}?(?:referenc|us|call|declar|expos|bind|bound|import|includ|exist|contain|depend)\w*`
    (case-insensitive), with a removed-only identifier among the next
    6 words.
  - **ORPHAN:** a match of
    `\b(?:dangling|unresolved|broken\s+(?:\w+\s+)?(?:binding|reference)s?)\b`,
    with a removed-only identifier anywhere in the same sentence.
- **Action:** like hedge demotion. The blocker moves, verbatim, to the
  end of the reviewer's `questions` or the engineer's `concerns`, after
  any hedge demotions. Each round records the count as
  `survival_demotions`. Demoted items can be recovered from the counts,
  so records stay replayable.
- **Scope:** the rule never fires without a diff, since the removed set
  is then empty.

**Development set** (tuned on, so optimistic): the 45 round-1 blockers
of fifth-measurement arm 1 and the sixth measurement, with the labels
recorded above.

- **Recall:** it demotes 7 of the 8 M2.
- **False demotions:** 0 of the 37 others (11 race, 4 in-flight gate,
  19 removal objections, 3 other).
- **The miss:** the borderline bbe168 #1 ("removed from header but
  referenced in QML").
- **The near miss:** 8e3c25 #2, a negative, contains "still
  references", but no removed-only identifier follows. The comment it
  cites is real.

**Known gaps** (deliberately not covered, since there is no dev
evidence for them):
- "but referenced in", "remains", "continues to use".
- Survivors named in prose ("the signal model") rather than by
  identifier.
- Claims whose identifier sits in another sentence than the marker.

**Held-out sets:**

- **A, v5 scored runs** (276bd0, e4d1b3, 6ce6c0; 10 blockers).
  - The labels come from the fourth measurement's table: M2 2, 6 and 0;
    TP 1, 0 and 1. That is 8 M2 and 2 TP.
  - Run 1's TP (the 10,000-frame freeze) is identified by content at
    scoring time.
  - The labels stand as recorded. A label that looks wrong under the
    sixth measurement's definition is reported, not changed.
- **B, no-pack runs** (014257 and 170208). These are 3 round-1
  thread-safety blockers with 0 M2, per the fourth and fifth
  measurements.
- **C, 10 new v6 samples** from the round-1 measurement mode.
  - Each blocker is labelled by hand with the sixth measurement's
    classes, against `8ffbf19`.
  - The labels are recorded here before the rule runs on them.
  - The labeller knows the rule. M2 labels rest on `git grep` facts,
    which limits that bias.

**Prediction:**

| Metric | Predicted |
|---|---|
| Valid blockers demoted (race, gate, TPs, other valid), A + B + C | **0** |
| B demotions | 0 of 3 |
| A recall | ≥ 4 of 8 M2 |
| C recall | ≥ 50% of its M2 |
| A + C recall | ≥ 50% |
| C removal objections demoted | ≤ 1 |
| C M2 per run (replication, no decision attached) | 0.2–0.9 (sixth: 0.5) |

**Basis:**
- The dev set gives 7 of 8 with no false demotions, so the prediction
  allows for shrinkage on unseen phrasing.
- The fourth measurement described v5's class as "signalModel() still
  declared", which STILL covers.
- Both markers need a removed-only identifier. The race and gate
  blockers either name surviving identifiers or make no survival claim.

**Decision rule:**

- **Ship:** zero valid blockers demoted in A–C, and A + C recall
  ≥ 50%. The rule goes into debates and measurements, and
  `JUDGE_VERSION` becomes `j3-survival-claims`.
- **Any valid blocker demoted:** do not ship. The case becomes a
  negative-control unit, and the held-out sets become dev. Revise the
  rule and predict again on fresh samples.
- **No false demotions, but recall < 50%:** the rule is too narrow. The
  missed cases move to dev; widen the rule, then predict again on fresh
  samples.
- **Removal objections demoted:** reported. They are blocking only
  above 2, since they react to the proposal mismatch (#21) and are not
  valid defect claims.

**Effect on later measurements:** if j3 ships, stored blockers no
longer hold the demoted M2. To stay comparable, the scored unit becomes
round-1 blockers after hedge demotion and *before* survival demotion.
The scorer rebuilds that from `survival_demotions`.

**Plan after review** (offline; no model runs except collecting C):

1. Add `demote_unverified_survival(agent_out, removed, concern_key)` to
   adjudication.py, as a pure function returning `(output, count)`.
   - Unit cases are taken verbatim from records, with the record id as
     provenance, as for the hedge units.
   - Positives: the 7 dev M2 it catches.
   - Negative controls: 8e3c25 #2, a gate blocker and a race blocker.
2. Have the scorer apply it to stored round-1 blockers and report what
   it would demote, per class. This is the replay.
3. Collect and label C, record the labels here, then replay over A, B
   and C and score against this table.
4. Only if it ships: wire the rule into `run_debate` and
   `run_round1_review`, and bump `JUDGE_VERSION`.

## Eighth Measurement — Arm H: No Hedging Ban

*Prediction recorded 2026-10-22, before any H sample was run.*

**Hypothesis:** the reviewer prompt's ban on
hedged language in blockers pushes the model into confident wrong
guesses.
- **The mechanism:** the rule checks wording. A model can comply by
  dropping the hedge word while keeping the claim, and nothing says a
  wrong blocker costs more than a question.
- **The history fits but proves nothing.** The ban arrived in
  `5a0ec9b`, between the baseline and the v1 re-run. In that re-run,
  hedged blockers fell from 3 to 0 with zero demotions, and
  confident-but-wrong blockers rose from 0 to 4. But that was one run
  against one, layer metadata changed at the same time, and those 4 are
  now flagged as probably real races.

**Change** (PROMPT_VERSION `v7-no-hedge-ban`, prompt fingerprint
`89af2eec5b06a619`):
- **Deleted, and nothing else changed:** the two prompt lines "Hedged
  language (may/might/could/possibly/suspected/appears/seems/uncertain)
  MUST NOT appear in blockers — such statements belong in 'questions'".
- **Kept:** the demotion guardrail, which becomes the cheap "I don't
  know" path because a hedged blocker turns into a question.
- **Also kept:** "A blocker is a DEMONSTRABLE violation … If you cannot
  cite the line and rule, it does not belong in blockers."
- **Side effect:** the probe and bake-off share `REVIEWER_SYSTEM`, so
  they change too. This measurement does not run them.

**Design:**
- **Samples:** 10 round-1 samples. Fixture, proposal text, models,
  settings and judge are as in the sixth measurement.
- **Comparison:** the sixth measurement (v6, 10 samples): 26 blockers,
  M2 5 in 3 runs, the race in 5 runs, the gate in 3, 1 hedge demotion
  (0.1 per run), 28 questions.
- **Unit:** the same as before: round-1 blockers from first attempts,
  as stored after hedge demotion.
- **Hedge-demoted items are labelled too.** They are recovered from
  the tail of `questions` using the `hedge_demotions` count. A demoted
  M2 is a direct sign the hypothesis holds; a demoted valid blocker
  (race, gate) is a cost (#12).

**Prediction** (my own expectation, not the hypothesis): the M2 look
like misreadings, so I expect hedging to rise without M2 falling much.

| Metric | Sixth (v6) | Predicted H |
|---|---|---|
| Hedge demotions per run | 0.1 | 0.3–1.5 |
| M2 per run, stored blockers | 0.5 | 0.2–0.7 |
| M2 among the hedge-demoted | — | 0–2 |
| Valid blockers hedge-demoted (race, gate) | 0 | 0–2 |
| Runs with the race, stored blockers | 5 of 10 | 3–7 |
| Blockers per run, stored | 2.6 | 1.8–3.2 |

**Decision rule** (on stored M2 per scored run):

- **≤ 0.2, with hedge demotions ≥ 0.3 per run: supported.** H's prompt
  stays, and G builds on it.
- **≥ 0.4: not supported.** The class is not forced confidence. Revert
  to the v6 prompt, and G builds on v6.
- **Between:** add 5 samples and apply the same thresholds. If the
  result is still between, treat it as not supported and record it as
  unresolved.
- **Override:** if more than 2 valid blockers are hedge-demoted, H is
  not adopted whatever the M2 result. That is recorded as a data point
  for #12, the hedge gate.

**Power caveat:** as in the sixth measurement, 10 samples against 10
detect only a large change. 5 M2 against ≤ 2 is a difference that
arises by chance about 1 time in 8.

### Results (scored 2026-10-22)

**Samples:** `coach_artifacts/measurement_round1_20261022_22*.json`, from
221300_927761 to 223504_eadc06, fingerprint `89af2eec5b06a619`.
- **9 of 10 scored.** a7e4eb is excluded: its first attempt ran away to
  the 12,288-token cap, and its 7 blockers came from the retry.
- **Time:** 24.5 minutes in all.

| Metric | Sixth (v6) | Predicted H | Observed H | Outcome |
|---|---|---|---|---|
| Hedge demotions per run | 0.1 | 0.3–1.5 | **0.11** (1 in 9) | **MISSED LOW** |
| M2 per run, stored | 0.5 | 0.2–0.7 | 0.33 (3 in 2 runs); 0.44 with the borderline case | HIT |
| M2 among the hedge-demoted | — | 0–2 | 0 | HIT |
| Valid blockers hedge-demoted | 0 | 0–2 | 0 | HIT |
| Runs with the race | 5 of 10 | 3–7 | 6 of 9 | HIT |
| Blockers per run, stored | 2.6 | 1.8–3.2 | 2.89 (26) | HIT |

**Decision rule:** the hypothesis is not supported.
- **The mechanism did not appear.** Without the ban the reviewer still
  did not hedge its blockers, so no extra claims reached the "I don't
  know" path. "Supported" also needs hedge demotions ≥ 0.3 per run.
- **M2 lands between the thresholds.** At 0.33 per run (0.44 with the
  borderline case), the rule calls for 5 more samples.
- **Those samples cannot reach "supported".** M2 ≤ 0.2 over 14 runs
  would need at most 2 M2, and 3 are already counted. They can only
  decide between "not supported" and "unresolved", and both mean
  reverting to v6. Whether to run them anyway is decided in the
  amendment below.

**Composition** (26 stored blockers):

| Run | Blockers | M2 | Composition |
|---|---|---|---|
| 927761 | 3 | 0 | the race; 2 × in-flight gate |
| ec3bc7 | 2 | 0 | 2 × in-flight gate |
| 9d7d20 | 1 | 0 | the race |
| 19c2e0 | 4 | 0 | the race; 2 × in-flight gate; deleted regression test |
| 766a37 | 3 | 0 | the race; in-flight gate; deleted regression test |
| b0756d | 3 | 0 | the race; in-flight gate; **the 10,000-frame freeze** |
| c83c91 | 3 | 1 | 1 deletion-consistency; 2 ABI objections to removed code |
| 051380 | 2 | 0 | the race; false `appendFrame` claim |
| eadc06 | 5 | 2 | 2 deletion-consistency; 8-byte decode shown as current (borderline M2); feature removal; speculative null dereference |

By class: the race 6 (6 runs), in-flight gate 8 (5 runs), freeze 1, M2
3, removal objections 3 (2 of them about the deleted regression test),
other 5. One item was hedge-demoted (c83c91): a speculative `uri8`
lifetime claim. It is false, since the named local outlives the
synchronous call, so the demotion was correct.

**The M2 blockers, checked against `8ffbf19`:**

- **eadc06 #3:** "Main.qml: UI references QtTune.signalModel … dangling
  QML binding". This is the sixth measurement's pattern again.
- **eadc06 #2:** "SignalListModel … removed from header but references
  still exist in comments and code". `SignalListModel` has no hits.
- **c83c91 #2:** "the comment 'Backpressure: bound the QUEUED backlog'
  references code that was removed". That comment exists only in the
  pre-state. It also makes the valid gate point, as bbe168 #5 did in
  arm 1.
- **Borderline, eadc06 #1:** it presents the removed
  `qttune_decode_signal(&def, frame->data, 8, &val)` call as current
  code at "Line 148-151". There is no decode call anywhere in the
  post-state `app/`. The earlier 8-byte blockers said the code was
  removed, so they were "other".

**Other false positives:**
- **051380 #2:** claims `appendFrame` lacks a
  `beginInsertRows`/`endInsertRows` pair. The post-state has the pair,
  then evicts with `beginRemoveRows`/`endRemoveRows`.
- **c83c91 #1 and #3:** C-ABI objections to C++ signatures in the
  removed `SignalListModel`.
- **eadc06 #5:** a conditional "potential null pointer dereference".
  "potential" is not in `HEDGE_PATTERNS`.

**Unpredicted shift, worth a replication before anything relies on
it:**
- **More valid blockers.** Race, gate and freeze blockers were 15 of 26
  (58%), against 11 of 26 (42%) at v6. The gate rose from 4 blockers
  in 3 of 10 runs to 8 in 5 of 9.
- **The freeze appeared.** The 10,000-frame freeze (b0756d #3) is the
  fourth measurement's run-1 TP, its first appearance since v5.
- **The deleted test returned.** Two blockers flag the removed
  `StreamingContinuesPastTenThousandFrames` test.
- **Feature-removal objections almost vanished:** 9 at v6, 1 here.
- **But other false positives rose,** from 1 to 5.
- **No prediction covered this,** N is 9 against 10, and a one-line
  deletion has no obvious route to these effects. So sampling variance
  is the first explanation.

### Amendment (2026-10-22): the extra samples are skipped; H is reverted

**Decision:** H is recorded as not supported, without
the 5 extra samples, since they cannot change the action. The reviewer
prompt goes back to the v6 text, ban included. The ninth measurement, G,
builds on v6, so it compares directly with the sixth. The unpredicted
composition shift stays an observation; nothing relies on it.

## Ninth Measurement — Arm G: Evidence-Quoted Blockers

*Design and prediction recorded 2026-10-22, before G was implemented
or run.*

**Idea:** make a guess expensive by checking it mechanically, not by
asking for confidence. The arm H result points the same way: the
reviewer does not hedge when it may, so its wrong blockers are not
self-flagged guesses. They are confident misreadings, and only a check
against the code catches those.

**Change** (PROMPT_VERSION `v8-evidence-quotes`, prompt fingerprint
`2e56c3a3c15d32f2`, JUDGE_VERSION `j3-evidence-quotes`; built on the v6
text, so the hedging ban stays):

- **Prompt:** each reviewer blocker becomes an object
  `{"claim", "file", "quote"}`. The rules say:
  - the quote must be copied exactly from that file's lines in the CODE
    DIFF, without the leading `+`, `-` or space;
  - blockers are checked mechanically, and one whose quote is not found
    is moved to questions;
  - a wrong blocker costs more than an open question, and a question
    costs nothing, so a blocker whose evidence cannot be quoted should
    be a question.
- **Judge** (adjudication.py, pure), run after normalization and
  before hedge demotion. A blocker stays a blocker only if all of
  these hold:
  - it names a file the diff touches. The `file` value is read up to
    its first space, `a/` and `b/` prefixes and a trailing `:line` are
    ignored, and a unique path suffix is accepted. A deleted file's
    `--- a/` path counts.
  - its quote is found in that file's diff lines, with both sides
    allowed and whitespace collapsed on both sides. Lines are read by
    hunk length, so a removed line that starts with `--` is not taken
    for a file header.
  - the quote has at least 8 non-space characters.

  A quote may skip text with `...` or `…`. Each fragment must then be
  found, and the longest must have at least 8 non-space characters. A
  leading diff marker and surrounding backticks or quotes are stripped.
  When a code context was supplied, a quote found in it also passes. A
  string blocker, with no quote, is demoted.

  *(Refined before implementation and before any G sample: the
  ellipsis and `file`-token details.)*

  Demoted blockers move verbatim, as their flattened text, to the end of
  `questions`, ahead of any hedge demotions. Each round records the
  count as `evidence_demotions`.
- **Unchanged:** the engineer prompt and output, the golden suite, the
  probe and the bake-off. None of them verify quotes.

**Known gap:** the check proves only that the quote exists in that file,
not that it supports the claim. A "Main.qml still references
signalModel" blocker that quotes the removed `LiveViewPage.qml` line
under the file `LiveViewPage.qml` passes. The check catches the class
only when the model's misattribution also reaches the `file` field.

**Design:** 10 round-1 samples; fixture, proposal text, models and
settings as in the sixth measurement, which is the comparison.

- **Unit:** stored round-1 blockers from first attempts, after both
  demotions.
- **Evidence-demoted items are labelled too:**
  - a demoted M2 is the mechanism working;
  - a demoted valid blocker (race, gate, freeze) is the cost.
- **M1 is not comparable:** quoted code puts identifiers into blocker
  text. It is reported without a prediction.

**Prediction:**

| Metric | Sixth (v6) | Predicted G |
|---|---|---|
| M2 per run, stored | 0.5 | ≤ 0.2 (0–2 in total) |
| M2 among the evidence-demoted | — | ≥ 2 |
| Valid blockers evidence-demoted | — | 0–3 |
| Runs with the race, stored | 5 of 10 | 3–7 |
| Blockers per run, stored | 2.6 | 1.5–3.0 |
| Evidence demotions per run | — | 0.3–1.5 |
| Raw blockers that carry a file and a quote | — | ≥ 80% |
| Samples excluded | 0 | 0–3 |

**Basis:**
- **M2 should fall.** In four of the five sixth-measurement M2, the
  claim names `Main.qml` and the evidence is the `LiveViewPage.qml`
  removal. A model that names the file it means fails the check.
- **Valid blockers already quote real lines,** for example
  `if (self->m_currentFrameCount >= FrameListModel::MaxFrames)`.
- **The cost will come from paraphrased quotes** and from code outside
  the hunks.

**Decision rule:**

- **Ship (keep v8 and j3):** stored M2 ≤ 0.2 per run, at most 2 valid
  blockers evidence-demoted, and the race in at least 3 runs.
- **M2 ≥ 0.4:** G does not fix the class. Revert, and choose between
  the parked #15 check and other options.
- **M2 ≤ 0.2 but more than 2 valid blockers demoted:** the recall cost
  is too high. Do not ship as is. Find out why the quotes failed, then
  revise and predict again.
- **M2 between 0.2 and 0.4:** add 5 samples and apply the same
  thresholds. If the result is still between, G is not shipped and is
  recorded as unresolved.
- **Raw blockers with a quote below 50%:** the model is not following
  the format. Fix the prompt before reading any other metric.

### Results (scored 2026-10-22)

**Samples:** `coach_artifacts/measurement_round1_20261023_00*.json`, from
003411_e18362 to 005021_c88bcd, fingerprint `2e56c3a3c15d32f2`.
- All 10 replies came on the first attempt, so all 10 are scored. No
  reply ran away; collecting them took 17 minutes.
- All 27 raw blockers came as `{claim, file, quote}`. 20 were kept and
  7 were evidence-demoted; nothing was hedge-demoted.

| Metric | Predicted G | Observed | Outcome |
|---|---|---|---|
| M2 per run, stored | ≤ 0.2 | 0.1 strict (1); 0.6 counting removed code described as current (6) | HIT strict, see below |
| M2 among the evidence-demoted | ≥ 2 | 0 | **MISSED** |
| Valid blockers evidence-demoted | 0–3 | **4** (3 gate, 1 race), plus 1 valid deleted-test objection | **MISSED HIGH** |
| Runs with the race, stored | 3–7 | 5 of 10 (10 blockers) | HIT |
| Blockers per run, stored | 1.5–3.0 | 2.0 | HIT |
| Evidence demotions per run | 0.3–1.5 | 0.7 | HIT |
| Raw blockers with a file and a quote | ≥ 80% | 27 of 27 | HIT |
| Samples excluded | 0–3 | 0 | HIT |

**Decision rule:** on the strict M2 count (0.1 ≤ 0.2) with 4 valid
blockers demoted (more than 2), the branch is "do not ship as is; find
out why the quotes failed; revise and predict again". G is not shipped.

**Composition:**

| Run | Kept | Evidence-demoted |
|---|---|---|
| e18362 | 2 × the freeze | deleted-test objection (quote `}`) |
| ec62e7 | — | in-flight gate |
| b7a5a1 | 2 × the race | — |
| 66371a | the race | the race |
| 3bee25 | 2 × the race | in-flight gate |
| eb1077 | 4 × removed code described as current | — |
| 074dfc | 2 × the race | — |
| 5cc2ba | removed code described as current; M2 | false "dangling pointer" (fabricated quote) |
| fe9ad9 | 3 × the race | — |
| c88bcd | 2 false claims with quotes that mix the diff's sides | in-flight gate; false "null check removed" |

Of the 20 kept blockers, 12 are valid (10 race, 2 freeze), against 11
of 26 at v6. The freeze, the fourth measurement's run-1 TP, appeared
for the second arm running.

**The deletion class changed form, not rate.**
- The explicit misattribution ("Main.qml still references
  `signalModel`") did not appear at all, so the check had no M2 to
  catch.
- Instead, 6 kept blockers in 2 runs describe the deleted signal path
  as current code, quoting only removed lines:
  - "`m_stagingBuffer` is accessed from both threads", in eb1077 and
    5cc2ba;
  - the hardcoded 8-byte `qttune_decode_signal` call;
  - the missing decode-error handling;
  - a C-ABI objection to the removed `setSignalSet`.
- One of them, 5cc2ba #2, says outright that "code still references"
  the removed `m_stagingBuffer`, so it is strict M2. The other five
  assert survival only implicitly, as H's eadc06 #1 did. They are
  counted as borderline.
- In all, 6 deletion-class blockers against v6's 5. The quotes exist
  (on the removed side), so the check passes them, as the recorded
  known gap expected.

### Amendment (2026-10-22): revise to G3, post-change quotes

**Decision:** G is not shipped. Its revision, G3, is
predicted and measured on 10 fresh samples. G's samples are now dev
data, and the replay above is not evidence for G3.

**Why the valid blockers failed:**
1. **Implementation error: the check matched against the diff in its
   interleaved order.**
   - A multi-line quote from one side is broken by the other side's
     lines in between. The removed `fetch_sub` line sits inside the
     post-state `invokeMethod(...)` lambda, so ec62e7 failed; c88bcd's
     quote of the removed gate block failed the same way.
   - The same flaw passed two false blockers whose quotes mixed both
     sides, c88bcd #1 and #2. The design said "either side", meaning
     one side at a time; the code did not do that.
2. **Shortened quotes.** 3bee25 dropped a line's trailing comment, and
   66371a skipped three lines without marking them.
3. **No evidence.** e18362's deleted-test objection quoted `}`. This
   fails as designed.

**Dev replay, not a measurement (biased: designed on these samples).**
A corrected matcher reads the two sides separately and matches each
quote line against consecutive non-blank lines of one side.
- **As-run check:** demotes 4 valid blockers and 2 FPs.
- **Corrected matcher:** demotes 1 valid blocker (66371a) and 4 FPs. The
  `}` objection is demoted either way.
- **Where the kept quotes sit:** all 6 deletion-class blockers quote
  only the removed side. Of the valid blockers, only c88bcd's gate
  quote does. Every other valid blocker quotes the post-change side
  (context or added lines).

## Tenth Measurement — Arm G3: Post-Change Quotes

*Design and prediction recorded 2026-10-22, before G3 was implemented
or run.*

**Idea:** a blocker is a claim about the code after the change, so its
evidence must be code that exists after the change. Removed lines are
evidence only of a removal. A blocker about removed code described as
current, the form the deletion class took in G, can no longer quote
anything.

**Change** (PROMPT_VERSION `v9-post-change-quotes`, prompt fingerprint
`2aa6ba56fca5f85e`, JUDGE_VERSION `j4-post-change-quotes`; built on
v8):

- **Prompt:**
  - The quote is "the code that shows it, copied exactly from the CODE
    DIFF as it reads after the change". It comes from unchanged or added
    lines, without the leading `+` or space.
  - Removed lines no longer exist and are not evidence. If the problem
    is caused by a removal, quote the code after the change that the
    removal leaves broken or unprotected.
  - Unchanged from v8: blockers are checked mechanically, a wrong
    blocker costs more than a question, and the hedging ban stays.
- **Judge:** the post-change text of each file is its context plus
  added lines, in order; removed lines are excluded.
  - The quote is split at ellipses into fragments, and each fragment
    into lines.
  - Each fragment's non-blank lines must match consecutive non-blank
    post-change lines of the file the blocker names. A quote line
    matches when it is a substring of its source line, after the diff
    marker is stripped and whitespace collapsed.
  - The longest quote line needs at least 8 non-space characters.
  - File matching is unchanged from G.
  - A supplied code context counts as post-change text for any file.
  - Demotion and the `evidence_demotions` count are unchanged.
  - This replaces G's matcher. It fixes G's interleaving error, accepts
    a line whose trailing comment the quote omits, and rejects quotes
    that mix the two sides.
  - *Refined before implementation and before any G3 sample:* a
    fragment also matches when its lines, joined, are a substring of
    the file's joined post-change lines. This covers a quote reflowed
    onto fewer lines. Hunks are kept apart in both forms, so a quote
    cannot join lines from two hunks.

**Unit and classes:** the unit is unchanged. The decision metric is the
whole deletion class:
- strict M2;
- blockers that describe code the diff removes as current, without
  acknowledging the removal, as in G's eb1077 and 5cc2ba.

G showed the class moving between these forms, so they are counted
together. Raw blockers, kept plus demoted, are reported as well, to
show whether the model still produces the class.

**Prediction:**

| Metric | Sixth (v6) | G | Predicted G3 |
|---|---|---|---|
| Deletion class per run, stored | 0.5 | 0.6 | ≤ 0.2 (0–2 in total) |
| Valid blockers evidence-demoted (race, gate, freeze) | — | 4 | 0–2 |
| Runs with the race, stored | 5 of 10 | 5 of 10 | 3–7 |
| Valid share of stored blockers | 42% | 60% | ≥ 70% |
| Other FPs, stored | 1 | 2 | 0–3 |
| Blockers per run, stored | 2.6 | 2.0 | 1.0–2.5 |
| Evidence demotions per run | — | 0.7 | 0.3–1.5 |
| Raw blockers with a file and a quote | — | 100% | ≥ 80% |
| Samples excluded | 0 | 0 | 0–3 |

**Basis:**
- In G, all 6 deletion-class blockers quoted removed lines only.
- 14 of the 15 valid blockers the corrected matcher keeps quoted
  post-change lines.
- The prompt now steers removal-caused problems toward post-change
  quotes, as G's ec62e7 and 3bee25 gate blockers already did.
- **Risk:** the model might keep the claim and swap in an unrelated
  post-change quote.

**Decision rule:**

- **Ship (v9 and j4 become the default):** the deletion class ≤ 0.2 per
  run, at most 2 valid blockers evidence-demoted, and the race in at
  least 3 runs.
- **Deletion class ≥ 0.4 per run:** quoting does not hold the class.
  Revert to v6 and j2, and take stock before any further variant.
- **Class ≤ 0.2 but more than 2 valid blockers demoted:** not shipped.
  This is the last revision in this line; the next step is a broader
  review, not G4.
- **Between 0.2 and 0.4:** add 5 samples and apply the same thresholds.
  If the result is still between, G3 is not shipped and is recorded as
  unresolved.
- **Raw blockers with a quote below 50%:** fix the prompt first.

**Power caveat:** v6 and G had 5 and 6 deletion-class blockers, a mean
of about 5.5 per 10 runs. If G3 changed nothing, a count ≤ 2 would
occur by chance about 9% of the time.

### Results (scored 2026-10-22)

**Samples:** `coach_artifacts/measurement_round1_20261023_01*.json`, from
012351_55c897 to 013952_2f2843, fingerprint `2aa6ba56fca5f85e`.
- All 10 replies came on the first attempt, so all 10 are scored. No
  reply ran away; collecting them took 18 minutes.
- All 27 raw blockers came as `{claim, file, quote}`. 18 were kept, 8
  evidence-demoted and 1 hedge-demoted.

| Metric | Sixth (v6) | G | Predicted G3 | Observed G3 | Outcome |
|---|---|---|---|---|---|
| Deletion class per run, stored | 0.5 | 0.6 | ≤ 0.2 | **0.1** (1) | HIT |
| Valid blockers evidence-demoted | — | 4 | 0–2 | **2** (1 gate, 1 race) | HIT, at the limit |
| Runs with the race, stored | 5 of 10 | 5 of 10 | 3–7 | 7 of 10 (14 blockers) | HIT |
| Valid share of stored blockers | 42% | 60% | ≥ 70% | **94%** (17 of 18) | HIT |
| Other FPs, stored | 1 | 2 | 0–3 | 0 | HIT |
| Blockers per run, stored | 2.6 | 2.0 | 1.0–2.5 | 1.8 | HIT |
| Evidence demotions per run | — | 0.7 | 0.3–1.5 | 0.8 | HIT |
| Raw blockers with a file and a quote | — | 100% | ≥ 80% | 100% | HIT |
| Samples excluded | 0 | 0 | 0–3 | 0 | HIT |

**Decision rule: ship.** All three conditions hold: the deletion class
is 0.1 ≤ 0.2 per run, 2 ≤ 2 valid blockers were demoted, and the race
appeared in 7 ≥ 3 runs. v9 and j4 become the default.

**Kept blockers (18):**
- **The race,** 14 in 7 runs.
- **The in-flight gate,** 3: 80f1be #2 and #4, and 6b4d1a #2. 80f1be #2
  states the freeze's root cause: the gate checks "processed frames
  instead of in-flight/queued frames; should bound queue backlog, not
  lifetime count".
- **One deletion-class blocker, 55c897 #1.** It makes the valid gate
  point but adds "the comment about MaxInFlightFrames is now
  meaningless". No such comment exists at `8ffbf19`. Its quote is
  unrelated post-change code, the `appendFrame` eviction loop. This is
  the risk the prediction recorded: a real quote that does not support
  the claim.

**Evidence-demoted (8):**
- **Deletion class, the mechanism working:**
  - 819df9 #e1 and #e3, which present the removed 8-byte
    `qttune_decode_signal` call as current;
  - 698a1c #e1, the same call in the past tense (borderline).
- **False positive:** 819df9 #e2, an `m_connected` "race" whose quoted
  code does not exist anywhere.
- **Feature-removal objection:** 55c897 #e3, the signal batching.
- **Valid, the cost:**
  - 55c897 #e1, a gate claim quoting removed header lines;
  - 2f2843 #e1, a race claim whose quote skipped three lines. The same
    run kept another race blocker.
- **Valid deleted-test objection:** 55c897 #e2 (the removed
  `forceFrameCountForTesting` hook and the regression test). It is
  reported apart from the race, gate and freeze count, as in G.

**Hedge-demoted (1):** 2eb07e #h1, an `m_guiNotifyCount` "race" between
two GUI-thread accesses. It is false, so the demotion was correct.

**What this shows:**
- **The model still produces the deletion class; the judge now
  removes it.** Raw blockers held 3 or 4 deletion-class claims, kept
  plus demoted. Only one survived, and it carried a quote that does not
  support it.
- **Stored blockers are the most precise of any arm,** 94% valid,
  against v6's 42% and G's 60%. A count of ≤ 1 deletion-class blocker
  when about 5.5 were expected occurs by chance about 3% of the time.
- **Valid demotions have two causes:** a removal-caused claim that
  quoted removed lines despite the prompt, and a quote that skipped
  lines.

**Costs and limits:**
- **A deleted test can no longer be a blocker.** Its lines exist only
  on the removed side. "This diff deletes the regression test" becomes
  a question.
- **The freeze was not named** as a consequence (H 1, G 2, G3 0),
  though 80f1be #2 gives its root cause.
- **Blockers concentrate on the race.** Recall beyond the race and the
  gate is untested on this fixture.
- **This is one fixture,** with 10 samples per arm. The stable corpus
  (#7) is needed before the precision claim generalizes.
- **The live golden suite has not been run with v9.** Its fixtures do
  not apply the evidence check, but they read the new blocker format.

## Evidence Reader j5 (2026-10-22)

**Decision:** the evidence check reads diffs with the shared
`diff_reader` (code review 2026-10-21, finding 12). Inside a hunk, lines
are still counted by the hunk header. Outside a hunk, a line is now read
by its first character. j4 read only lines inside counted hunks, which
had two consequences:
- A diff without `@@` headers, such as a hand-written snippet passed
  with `--diff`, had no post-change lines. Every reviewer blocker on it
  was demoted, so the reviewer could never block such a diff.
- A file header ending in a tab and a timestamp (`diff -u`) was not
  read as a header.

Otherwise j5 is j4.

**Effect on recorded results:** none. Every record with a diff reviewed
the bridge fixture, whose hunks all have headers. On it, the evidence
sources are identical under j4 and j5. So are the pack text and every
request: compared byte for byte on 2026-10-22 for a fake-driven
three-round debate, a round-2 agent failure and a measurement. The
eighth to tenth measurements stand under j5.

## Hedge Check j6 (2026-10-22)

**Decision:** the hedge check reads a reviewer blocker without its
quote. Since v9 a blocker carries the code it quotes, and through j5
the regex read the whole flattened blocker. So a hedge word in quoted
code, such as a `// may be null` comment, demoted a verified blocker.
From j6 the regex reads every field but the quote. Plain-string
blockers, the engineer's included, are read whole as before. This is
the minimum of backlog #12, from code review 2026-10-21, finding 9.

**Replay over the records with quoted blockers** (arms G and G3):
- **No kept blocker can change.** The check reads less text than
  before, so it can only demote fewer blockers.
- **G has no hedge demotions.**
- **G3 has one,** 2eb07e #h1: "…potentially accessed from QML/GUI
  thread…". The hedge word is in the claim, so j6 demotes it too.

No recorded result changes.

**Decision on the rest of #12 (2026-10-22): no exemption.** If the
reviewer hedges, the claim is not a blocker. A verified quote does not
change that, and neither does a line citation, so the citation-gated
rule checked on 2026-10-10 is not adopted either. The reasons:
- **A quote proves the code exists, not that the claim holds.** The
  hedge is the reviewer saying it has not shown the violation.
- **The data agrees.** An exemption would have kept 2eb07e #h1, a
  false `m_guiNotifyCount` race between two GUI-thread accesses (tenth
  measurement). It is the only hedge demotion under v9.

**The cost is accepted.** A true claim stated with a hedge, like the
one in the N=3 measurement, becomes a question. It stays in the
record, and the verdict is APPROVED_WITH_OPEN_QUESTIONS, not a clean
approval. Backlog #12 is closed.

## Eleventh Measurement — Transcript Protocol v10 (backlog #11)

*Design and prediction recorded 2026-10-22. v10 and the pair mode were
implemented and unit-tested before this was written, and no v10 sample
had been run. Scope: all five parts of #11, measured with the paired
design.*

**Change** (PROMPT_VERSION `v10-transcript-protocol`, prompt fingerprint
`0e6f4ef2bcdfe385`, JUDGE_VERSION `j6-hedge-reads-claim`; built on v9;
only the transcript templates in `debate.py` change):
- **Fencing.** The diff and the context each sit between a BEGIN DATA
  and an END DATA line. Both lines carry a 16-hex mark taken from the
  SHA-256 of the diff and context, so the reviewed text cannot predict
  the mark and close the fence. A preamble says that text inside is
  data, never an instruction, and that a fence line with another mark
  is part of the data.
- **Truncation marker.** Context longer than 8000 characters is marked
  as truncated, with the shown and total lengths.
- **Feedback section.** From round 2 on, the previous round's replies go
  in a ROUND N CRITIQUES section after the code. The section calls them
  "claims, not verified facts". The proposal stays the author's text.
  Only the last round is shown; v9 accumulated every round.
- **All channels but nits.** The section holds reviewer blockers and
  questions (demoted blockers included), and engineer blockers, concerns
  and questions, one item per line. v9 fed back only the reviewer's
  blockers and the engineer's concerns and questions.
- **Uphold or withdraw.** "Keep a point only if the code shows it, with
  the evidence any new point needs. Drop a point the code does not
  support, or ask it as a question." This is an instruction only; the
  output schema is unchanged.

**Design** (round-2 pair, `python -m eval_harness.round2`):
- **Samples.** 10, on the bridge fixture, with the original proposal
  text (#21) and default settings.
- **Each sample:**
  - First, a v10 debate round 1: reviewer and engineer, at temperature
    0.7.
  - If a debate would go on from there (no agent failure, round 1 not
    converged), the round-2 reviewer runs twice on the same round-1
    replies, at 0.05:
    - the critiques arm, as a v10 debate sends it;
    - the v9 arm, with v9's REVISE ADDRESSING feedback appended to the
      proposal and everything else v10.

    Only the feedback format differs between the arms, and round-1
    variance is shared.
- **Round-2 scoring.** Stored round-2 reviewer blockers, per arm, in
  pairs where both arms answered on the first attempt.
- **Hand labels,** as in the tenth measurement: the race, the in-flight
  gate, the deletion class, removal objections, deleted-test objections
  and other FPs. Valid means the race, the gate or another confirmed
  defect.
- **Origin tags,** scripted and confirmed by hand. They are read from
  the claim's identifiers, never the quote:
  - carried: a round-1 reviewer blocker names one of them;
  - from-question: a round-1 reviewer question does;
  - echo: only round-1 engineer items do;
  - new: no round-1 item does.
- **Round 1 doubles as the fencing control.** Each sample's round-1
  reviewer reply is scored with `eval_harness.round1` (first attempts)
  against G3.

**Prior:** 15 archived debates reached round 2 (v3 to v5.2), all with
v9-style feedback and string blockers. Of their 41 round-2 reviewer
blockers, 39 carried round-1 subjects, 1 echoed an engineer item and 1
was new. Round 2 is mostly persistence, so this is a non-inferiority
check. v10 is a protocol fix: feedback no longer reads as the author's
text, and the injection surface is fenced. It ships if it does no harm.

**Prediction:**

| Metric | Reference | Predicted |
|---|---|---|
| Round 1: deletion class per run, stored | G3 0.1 | ≤ 0.2 |
| Round 1: runs with the race, stored | G3 7 of 10 | 3–9 |
| Round 1: valid share of stored blockers | G3 94% | ≥ 70% |
| Round 1: blockers per run, stored | G3 1.8 | 1.0–2.5 |
| Samples reaching round 2 | — | 6–9 of 10 |
| Pairs compared | — | 5–9 |
| v9 arm: share of round-2 blockers carried | prior 95% | ≥ 80% |
| Critiques arm: share carried | — | ≥ 70% |
| Race kept in round 2, of pairs whose round 1 stored it | — | v9 arm: all but at most 1; critiques arm ≥ v9 arm − 1 |
| Round-2 blockers per pair | — | critiques arm ≤ v9 arm + 0.5 |
| Echo and from-question FPs, confirmed | prior 1 | critiques arm ≤ v9 arm + 1 |
| Valid share of round-2 blockers | — | both ≥ 80%; critiques arm ≥ v9 arm − 10 points |

**Decision rule:**
- **Ship (v10 stays the default)** if both hold:
  - round 1 holds: the deletion class ≤ 0.2 per run, the race in ≥ 3
    runs, and a valid share ≥ 70%;
  - the critiques arm is not worse: race retention ≥ the v9 arm's − 1
    pair, a valid share ≥ the v9 arm's − 10 points, and confirmed echo
    and from-question FPs ≤ the v9 arm's + 1.
- **Round 1 fails:** the fence harms round 1. Revert the fence and the
  truncation marker, keep the feedback change if its own conditions
  hold, and re-measure round 1.
- **Round 2 fails:** revert the feedback to v9's format, and keep the
  fence if round 1 holds.
- **Fewer than 4 pairs compared:** add 5 samples before deciding.

**Power caveat:** with 5–9 pairs only large differences show, such as
the race lost in 2 or more extra pairs, or 2 or more extra FPs. The
ship rule is non-inferiority within those margins, not a test for an
improvement.

### Results (scored 2026-10-22)

10 samples, `coach_artifacts/measurement_round2_20261023_*.json` (record
IDs are UTC). Every sample reached round 2. 4 pairs were excluded
because a round-2 reply came from a retry (77f24d, 97c2dd, 6e7367,
410daf), which leaves 6 pairs. Hand labels used the post-state at
`8ffbf19`.

**Round 1, the fencing control** (10 first attempts, 25 stored
blockers):
- the race: 17 blockers, in 10 runs;
- the in-flight gate: 3 (751a8f #1, 97c2dd #2, 5ef90b #2);
- the deletion class: 1, c55779 #4 (`Main.qml` "references removed
  SignalListModel", with an unrelated quote);
- other FPs: 4. 6e7367 #1 says `handleFrameInternal` does not append
  frames, though its own quote shows it does. 410daf #3 says
  `appendFrame` lacks `beginInsertRows`, which is at line 50. c55779 #2
  and #3 claim races on `m_lastReportedDropped` and `m_guiNotifyCount`,
  which only the GUI thread touches.

8 blockers were evidence-demoted. One was valid, 5ef90b #e1, a race
whose quote joined a comment to the line; the same run kept another
race blocker. Raw deletion-class blockers, kept plus demoted, numbered
3: c55779 #4, 407954 #e2 and c55779 #e1.

**Round 2** (6 pairs; origin tags confirmed by hand):

| | Critiques arm | v9 arm |
|---|---|---|
| Stored blockers | 14 (2.33 per pair) | 15 (2.5 per pair) |
| Race, gate, FP | 13, 0, 1 | 11, 3, 1 |
| Carried from round 1 | 14 of 14 | 15 of 15 |
| Echo or from-question FPs | 0 | 0 |
| Race kept, of 6 pairs | 6 | 6 |
| Gate kept, of the 2 pairs whose round 1 stored it | 0 | 2 |
| Round-1 FPs withdrawn (c55779 #2 and #4) | 2 | 2 |
| Valid share | 93% | 93% |
| Hedge-demoted | 1 | 0 |
| First attempts that ran away (all 10 samples) | 3 | 1 |

The one scripted echo tag (v9 arm, 5ef90b #2) is the reviewer's own
round-1 gate blocker, reworded with the engineer's "high-frequency
CAN-FD bursts". The critiques arm's hedge demotion (c55779 #h1) is a
gate claim echoing engineer concern E-c1, worded "could cause". In 6b1987
the v9 arm stated the gate on its own (#3); the critiques arm kept only
round 1's race-and-gate hybrid. In round 1, 0 of the 20 first attempts
ran away.

| Metric | Predicted | Observed | Outcome |
|---|---|---|---|
| Round 1: deletion class per run | ≤ 0.2 | 0.1 | HIT |
| Round 1: runs with the race | 3–9 | 10 | MISSED HIGH |
| Round 1: valid share | ≥ 70% | 80% (20 of 25) | HIT |
| Round 1: blockers per run | 1.0–2.5 | 2.5 | HIT, at the limit |
| Samples reaching round 2 | 6–9 | 10 | MISSED HIGH |
| Pairs compared | 5–9 | 6 | HIT |
| v9 arm: share carried | ≥ 80% | 100% | HIT |
| Critiques arm: share carried | ≥ 70% | 100% | HIT |
| Race kept | v9 all but ≤ 1; critiques ≥ v9 − 1 | 6 and 6 of 6 | HIT |
| Round-2 blockers per pair | critiques ≤ v9 + 0.5 | 2.33 vs 2.5 | HIT |
| Echo and from-question FPs | critiques ≤ v9 + 1 | 0 and 0 | HIT |
| Valid share, round 2 | both ≥ 80%; critiques ≥ v9 − 10 | 93% and 93% | HIT |

**By the recorded rule: ship.** Round 1 holds, and the critiques arm is
not worse on any registered metric.

**Outside the rule, two costs, both in the critiques arm:**
- **It dropped the in-flight gate,** the freeze's root cause, in both
  pairs whose round 1 stored it. The v9 arm kept it in both. The likely
  cause is "keep a point only if the code shows it": the gate is a
  defect caused by a removal, the case a quote shows least directly.
- **It ran away on 3 of 10 first attempts,** against 1 of 10 for the
  v9 arm. Its thinking tails re-check open-endedly: "Let me also check…"
  and "Now let me also check for the … removal".

On this fixture the section showed no benefit: both arms withdrew the
same two round-1 FPs. Each cost rests on very few samples (2 pairs, and
3 against 1 runaways).

**Round 1 against G3:** 4 other FPs against G3's 0, and 2.5 blockers
per run against 1.8. All 4 quote real post-change code with a false
claim. The race appeared in every run. Variance between two sets of 10
samples can account for the difference, but this is the case to watch
for the fence.

### Amendment (2026-10-22): fence only (v10.1)

The fence and the truncation marker shipped without the CRITIQUES
section. This deviates from the recorded rule, toward the measured
side. PROMPT_VERSION `v10.1-fenced-input` (prompt fingerprint
`30f7aeff90e8ec76` for debates):
- round 1 is v10's, measured above;
- round 2 is the v9 arm's request, which a test pins as identical.

So nothing unmeasured ships. The CRITIQUES section stays in `debate.py`
as the pair measurement's candidate arm only, and backlog #11 keeps it
with two design constraints:
- a defect caused by a removal must stay quotable as a blocker;
- the check instruction must not invite open-ended re-checking.

## Input Checks j7 (2026-10-23)

**Decision:** before any model call, the debate checks its input, and
the evidence check reads diffs without file headers. These are findings
13, 16, 17 and 18 of the 2026-10-23 code review. JUDGE_VERSION is
`j7-input-checks`. No prompt changed.
- **No code, no review.** With no diff and no context, the debate ends
  as `NO_INPUT - MANUAL_REVIEW_REQUIRED` without a model call. Under j6
  a clean reply to no code approved it for merge, against the
  fail-closed convention.
- **Diff lines outside any file header are evidence for any file
  name,** as a supplied context is. Under j6 such a diff had no
  evidence, so every reviewer blocker on it was demoted, and the debate
  could approve in round 1. This is j5's reasoning for hunkless diffs,
  one step further. It was chosen over refusing such a diff.
  - A `+++` header that follows no `---` now starts a new file. Under
    j6 the next file's lines also counted as the previous file's.
- **Oversized input is refused** as `INPUT_TOO_LARGE -
  MANUAL_REVIEW_REQUIRED`.
  - The round-1 request (the larger agent's system prompt plus the
    transcript) is estimated at 3 chars per token. That is below every
    ratio on record: 3.43–3.52 for laguna-xs-2.1 and 3.21–3.30 for
    gemma4:12b, over 134 calls.
  - The limit is `NUM_CTX - NUM_PREDICT`, 12,288 tokens. Every reply
    keeps its full output cap, so `NUM_PREDICT`, not the window, ends a
    runaway, and Ollama never has to cut the prompt.
  - **Cost:** with the bridge fixture's prompt, pack and proposal, a
    diff above about 30K chars is refused. The fixture's request is
    33,294 chars, estimated at 11,098 tokens.
  - Later rounds grow by the feedback only and are not checked again.
    An overflow there ends on `done_reason=length` and fails closed.
  - Records keep the estimate as `metadata.input_check`, so it can be
    calibrated against the telemetry's `prompt_eval_count`.
- **A reply's own `blocker_evidence` key is dropped** in normalization.
  An engineer reply carrying one reached the hedge check. A list of
  strings crashed the debate, and confident claims in it kept a hedged
  blocker.
- **Deliberately unchanged:** the hedge check still reads every
  blocker field but the quote, the `file` path included. No recorded
  path has tripped it, so it is revisited only if one does.

**Effect on recorded results:** none.
- **Inputs.** All 62 records with a diff hash reviewed the bridge
  fixture, which has file headers. Its evidence sources are identical
  under j6 and j7. The four older records without hashes reviewed the
  same fixture, or QtTune's core.h as context. No record had empty
  input.
- **Sizes.** The largest round-1 reviewer request on record is 33,294
  chars, under the 36,864-char limit.
- **Replies.** Stored replies cannot show whether an engineer ever
  sent `blocker_evidence`, because the hedge check removed the key
  before storing. A crash would have left no record.
- **Requests.** Five fake-driven runs on the bridge fixture sent
  byte-identical requests before and after the change: a three-round
  debate, a round-2 agent failure, a measurement, a round-2 pair and a
  context-only header review. Their records differ only in
  `judge_version`, the new `input_check`, and the dropped
  `audit_trail.validation_method`.

## Golden Suite Routing (2026-10-23; backlog #14)

*Recorded before the suite's first live run since v9.*

**Decision:** each golden model fixture is reviewed as a debate's round-1
reviewer reviews it (`debate.review_round1`). Its snippet is the CODE
CONTEXT, inside the fence, with its layer note. The evidence check and
hedge demotion then run as in a debate. Until now the suite sent the
bare snippet as the whole message. Since v9 the reviewer prompt asks for
a quote "copied exactly from the CODE DIFF", which that message did not
contain. Nothing checked quotes, so a pass counted blockers that a
debate would demote.
- **Proposal:** the fixed, neutral *"Review the code in the CODE
  CONTEXT."* A fixture's name, such as `buffer_overflow_can_fd`, would
  tell the reviewer what to find.
- **Temperature: 0.05 on the first attempt, as before.** The suite
  stays a repeatable reviewer unit test. A debate's
  round 1 samples at 0.7, so a golden result describes the reviewer at
  low temperature, not a debate's round-1 sample.
- **Run log:** `gold_tests/run_*.json` now records the prompt and judge
  versions, the model, the temperature and the proposal. Each fixture
  also records its evidence and hedge demotion counts and its attempts.
- **Prediction for the first run** (drafted with the change; open to
  amendment until the run): the three fixtures pass as on
  2026-10-10. The CAN-FD and ABI fixtures each have a quotable line, and
  the clean header has nothing to block. A failure on a fixture
  expected to block would show the evidence check demoting a real hit
  and would need reading before anything changes.
- **Fixtures shared with the bake-off (amended 2026-10-23, before the
  first run).** The suite and the bake-off now read the same snippets
  from `review_fixtures.py`. The two copies of the ABI fixture differed
  by one space before "(public C ABI header)"; the bake-off's text was
  kept, so the bake-off's input is unchanged and the suite's ABI fixture
  gains a space. The prediction stands.

**Result (2026-10-23, first run; PROMPT_VERSION
`v10.2-unknown-layer-note`, judge j7): HIT, 10 of 10.** The 7 hedge units
pass. Each model fixture was answered on the first attempt, with no
evidence or hedge demotion. The CAN-FD and ABI fixtures were blocked, and
the clean header was not. The run log is
`gold_tests/run_20261023_180817.json` (gitignored). It keeps pass flags
and counts, not the blocker texts.

## Unknown-Layer Note v10.2 (2026-10-23)

**Decision:** input with no file path gets the unknown-layer note, "apply
all rules conservatively", and records layer `unknown` (code review
2026-10-23, finding 19). A path comes from the first `+++` header, or
else from a `//` comment in the first 20 context lines. Without one, a
review had no layer note at all. Since j7 a diff without file headers
can be blocked, so it is a real review input. PROMPT_VERSION is
`v10.2-unknown-layer-note`. The judge is unchanged.

**Effect on recorded results:** none. Every record with a diff hash
stores layer `bridge`, from the bridge fixture's header. Of the four
older records, three reviewed that fixture, and header review 194320
reviewed core.h, which names its path on line 1. Input with a path is
sent byte for byte as under v10.1, so the bridge fixture's debate
fingerprint stays `30f7aeff90e8ec76`, and v10.2 runs on it compare with
v10.1 runs.

## Re-Triage of the Early Runs (2026-10-23; backlog #17)

**Why:** the first six scored runs were triaged before the 2026-10-13
forensics established the fixture's post-state, against maintained
QtTune. The fourth measurement's re-adjudication flag asked for the
thread-safety labels to be redone. This section redoes every blocker of
those runs, with the classes used since the sixth measurement, against
the post-state at `8ffbf19`. The original tables above stay as recorded.

**Classes:** valid means **the race** (`m_currentFrameCount`, read on the
worker thread in `onFrame`, written on the GUI thread) or **the gate**
(the removed in-flight bound; the cumulative check that replaces it
bounds nothing). The false positives are:
- **layer:** a Qt include in bridge code;
- **removed code:** a defect in code the diff removes, presented as
  current;
- **deletion class:** a claim that removed code survives;
- **removal objection:** objects to a removal (the fifth measurement's
  definition);
- **other.**

Each run keeps its original unit. The baseline and v1 counted all three
rounds of one debate. The feedback loop was not yet wired, so each round
resampled round 1 (see the erratum). The fourth measurement counted
round 1 of three debates.

**Baseline, 203917** (12 blockers). The 2026-10-07 triage kept class
counts only. By elimination, its 7 layer-rule FPs were round 1's #1–#5,
#7 and #8.

| Blocker | Claim | 2026-10-07 | Re-triage |
|---|---|---|---|
| R1 #1–#3 | Qt headers in qttunebridge.h/.cpp | layer | layer |
| R1 #4 | `onFrame` reads non-atomic `m_currentFrameCount` unsynchronized | layer | **the race** |
| R1 #5 | `handleFrameInternal` writes `m_currentFrameCount` without a mutex | layer | **the race**, write side |
| R1 #6 | `m_lastReportedDropped` is non-atomic | pedantic | other: GUI thread only |
| R1 #7 | `qttune/signals.h` still included | layer | deletion class: the include is removed |
| R1 #8 | `data_length` used without a CAN/CAN-FD size check | layer | other: `data` is an inline 64-byte array |
| R2 #1 | `frame->data` may point to freed stack memory | definition | other: the copy is deep |
| R2 #2 | anonymous structs unsafe across the C ABI | definition | other |
| R3 #1 | `qttune_decode_signal` gets a hardcoded 8 | **real defect** | removed code |
| R3 #2 | `setSignalSet` takes `void*` | definition | removed code |

**v1, 014257** (6 blockers): R1 #1, the hardcoded 8, was the real
defect and is removed code. R1 #2, a shallow-copy use-after-free, is
other. R2 #1–#2 and R3 #1–#2, the four "confident-but-wrong" blockers,
are **the race**.

**Control, 170208** (1 round-1 blocker, 5 in all): every one is **the
race**.

**Fourth measurement, v5** (10 round-1 blockers):

| Blocker | Claim | 2026-10-13 | Re-triage |
|---|---|---|---|
| 276bd0 #1 | signal batching removed without replacement | deletion-consistency | removal objection |
| 276bd0 #2 | in-flight tracking removed, so the queued backlog is unbounded | deletion-consistency | **the gate** |
| 276bd0 #3 | the check compares the cumulative count, not the queued backlog | TP | **the gate** (the TP stands) |
| e4d1b3 #1–#6 | removed members and methods "still declared" | deletion-consistency | deletion class; none is in the post-state |
| 6ce6c0 #1 | the race | TP | **the race** |

**Result:**

| Run | Unit | Valid before | Valid after |
|---|---|---|---|
| Baseline 203917 | 3 rounds | 1 of 12 (the 8-byte decode) | **2 of 12** (the race) |
| v1 014257 | 3 rounds | 1 of 6 (the 8-byte decode) | **4 of 6** (the race) |
| Control 170208 | round 1; 3 rounds | 0 of 1; 0 of 5 | **1 of 1; 5 of 5** (the race) |
| v5, 3 runs | round 1 | 2 of 10 | **3 of 10** (the gate 2, the race 1) |

**What changes:**
- **The thread-safety false positives were the race.** v1's four
  "confident-but-wrong" blockers and the control's blockers are true
  positives. So the fourth measurement's headline result, "thread-safety
  FP class collapsed in 3/3 runs", removed no false positives. With the
  pack, the race was missing from every channel of round 1 in runs 1 and
  2, and run 3 still found it. Without a pack, it had appeared in the
  baseline, in v1 and in the control. The pack's stale call site, the
  post-fix hand-off for code the diff reverts (code review 2026-10-21,
  finding 1), may have suppressed
  it; three runs cannot tell.
- **The 8-byte decode was the only true positive of the baseline and
  v1, and it is in removed code.** It is a real QtTune bug, later fixed.
  But the fixture deletes the call, and the post-state has no decode
  call, so as a blocker on this diff it is wrong. Labels from the fifth
  measurement on already say so ("8-byte decode in removed code").
- **The layer note removed 3 false positives, not 7.** The other 4 of
  the baseline's layer-rule count were the race twice, a deletion-class
  claim and an other FP.
- **The gate sub-class dates from v5, not v6.** 276bd0 #2 was counted
  as deletion-consistency. 276bd0 #3, the run-1 TP, names the freeze's
  cause, the cumulative check. It does not name the freeze itself: the
  "drops every frame permanently after 10,000 frames" wording and the
  deleted test in the fourth measurement's description came from the
  triage and from the run's round-2 nit. Its confirmation as the
  freeze's cause stands. So b0756d (eighth measurement) is the first blocker
  that states the freeze, not its first appearance since v5, and the
  sixth measurement's remark that the gate blockers do not name the
  freeze applies to 276bd0 #3 as well.
- **The two bugs the review "missed".** The 2026-10-07 triage found two
  defects the reviewer did not report:
  - Last-write-wins in the staging buffer is in removed code:
    `m_stagingBuffer` exists only on removed lines.
  - The dropped-frame report starving under saturation is in the
    post-state. The drop count reaches QML only from
    `handleFrameInternal`. That function stops running once the
    cumulative check drops every frame, so the displayed count freezes
    with the frames. It is a symptom of the freeze, not a third bug.

  So the post-state has two known defects, the race and the
  gate-and-freeze. No exhaustive triage of it has been done.

**Effect on later measurements:** none. From the fifth measurement on,
blockers were labelled against `8ffbf19`, and from the sixth with these
classes.

**Process note:** this re-triage read the blocker texts of the seventh
measurement's held-out sets A (the v5 runs) and B (014257 and 170208).
That rule stays frozen as recorded. If #15 is ever scored, A and B are
no longer unseen by the labeller.

## Twelfth Measurement — Feedback Section v11 (backlog #11)

*Design and prediction recorded 2026-10-23, before any v11 sample was
run. Drafted in the 2026-10-23 code review (finding 9) and approved as
drafted: the template text, 10 samples with the +5 rule, and the gate
condition with one pair read by hand. v11 was implemented and
unit-tested before this was written.*

**Change** (PROMPT_VERSION `v11-critiques-candidate`, pair-record prompt
fingerprint `87997863073facd8`, JUDGE_VERSION `j7-input-checks`): only
`CRITIQUES_TEMPLATE` in `debate.py` changes, and only the pair
measurement's candidate arm sends it. Debates still send v10.2's
requests: their fingerprint stays `30f7aeff90e8ec76`. What changes from
v10, and why:
- **A reviewer blocker stands unless the code contradicts it.** v10
  said "keep a point only if the code shows it", so each point had to be
  proven again. The gate did not survive that, because the code does
  not show a removed part directly.
- **No re-confirmation.** Every stored reviewer blocker has passed the
  evidence check, and the section now says so. It asks the reviewer not
  to search the diff again to re-confirm one. The runaway tails in the
  eleventh measurement were this search: "Let me also check…".
- **A removal-caused defect is quoted from the code that now runs
  without the removed part.** That is how the round-1 gate blockers
  that survived were quoted: 751a8f R#1 quoted the
  `QMetaObject::invokeMethod(…, Qt::QueuedConnection)` call that no
  longer has a gate.
- **Kept from v10:** its own section after the code, so feedback no
  longer reads as the author's text; the last round only; every channel
  but nits, engineer blockers included. v9's feedback omits engineer
  blockers, which alone keep a debate going.

```
ROUND {round_num} CRITIQUES (what the agents said last round):
Reviewer blockers (each quote was checked against the code):{reviewer_blockers}
Reviewer questions:{reviewer_questions}
Engineer blockers:{engineer_blockers}
Engineer concerns:{engineer_concerns}
Engineer questions:{engineer_questions}
A reviewer blocker above stands unless the code contradicts it; then
drop it, or ask it as a question. Its quote was already checked, so do
not search the diff again to re-confirm it. A defect that a removal
causes is quoted from the code that now runs without the removed part.
Any other point becomes a blocker only with the evidence your
instructions require.
```

**Risk:** "stands unless the code contradicts it" may keep false
blockers that v10 withdrew. In the eleventh measurement both arms
withdrew the same two round-1 FPs (c55779 #2 and #4).

**Design:** the eleventh's, unchanged (`python -m eval_harness.round2`).
- **Samples:** 10, on the bridge fixture, with the original proposal
  text (#21) and default settings. Add 5 samples if fewer than 5 pairs
  are compared, or if fewer than 2 compared pairs stored the gate in
  round 1. If the gate condition still has fewer than 2 such pairs after
  that, the rule cannot test it. The decision is then made outside the
  rule and recorded as an amendment.
- **Arms:** v11 (recorded as `critiques_section`) against the v9 arm, a
  debate's own round 2, on the same round-1 replies.
- **Round 1** is v10.2's, which on this fixture is byte for byte
  v10.1's and v10's. So it also replicates the eleventh's round 1, where
  the fence showed 4 other FPs against G3's 0.
- **Scoring and labels** as in the eleventh: first-attempt pairs only;
  labels for the race, the gate, the deletion class, removal objections,
  deleted-test objections and other FPs; origin tags confirmed by hand.
  Hand labels use the post-state at `8ffbf19`.
- **New registered metric:** round-2 first attempts that ran away (hit
  `NUM_PREDICT`), per arm, over every sample that reached round 2. A
  runaway's retry excludes its pair, so the compared pairs alone would
  hide it. `eval_harness.round2 score` counts them since 2026-10-23; on
  the eleventh's records it gives 3 and 1, the hand count.
- **Records:** `coach_artifacts/measurement_round2_*.json` with the
  fingerprint above. The eleventh's carry `0e6f4ef2bcdfe385`, so score
  the two sets apart.
- **Cost:** about 2 hours on the RTX 3060. Each sample makes three
  reviewer calls and one engineer call, at 1–4 minutes each; a runaway
  adds 3–5 minutes.

**Prediction:**

| Metric | Eleventh: v10 arm / v9 arm | Predicted for v11 |
|---|---|---|
| Round-2 first attempts that ran away, all samples | 3 / 1 of 10 | ≤ the v9 arm's + 1 |
| Gate kept, of compared pairs whose round 1 stored it | 0 / 2 of 2 | in every pair where the v9 arm keeps it |
| Race kept, of compared pairs | 6 / 6 of 6 | ≥ the v9 arm's − 1 |
| Round-1 FPs withdrawn | 2 / 2 | ≥ the v9 arm's − 1 |
| Echo and from-question FPs, confirmed | 0 / 0 | ≤ the v9 arm's + 1 |
| Valid share of round-2 blockers | 93% / 93% | both ≥ 80%; v11 ≥ the v9 arm's − 10 points |
| Round-2 blockers per pair | 2.33 / 2.5 | ≤ the v9 arm's + 0.5 |
| Round 1 (replication) | v10.1: deletion 0.1 per run, race 10 of 10, valid 80%, other FPs 0.4 per run | deletion ≤ 0.2 per run, race in ≥ 3 runs, valid ≥ 70%; other FPs reported |

**Ship rule:** v11 replaces v9's feedback in debates if all of these
hold:
- runaways are at most the v9 arm's + 1;
- the gate is dropped in at most one pair where the v9 arm keeps it,
  and that pair is read by hand and reported. In 751a8f, v10 reworded
  the gate as a race instead of dropping it;
- the eleventh's race, valid-share and echo conditions: race retention
  ≥ the v9 arm's − 1 pair, a valid share ≥ 80% in both arms and ≥ the
  v9 arm's − 10 points, and confirmed echo and from-question FPs ≤ the
  v9 arm's + 1.

If v11 ships, debates send the section from round 2 on, PROMPT_VERSION
is bumped again, and the debate fingerprint changes. If it does not, the
section is not tried a third time. #11 then narrows to the one defect
left in v9's feedback, the omitted engineer blockers. Adding them to
`FEEDBACK_TEMPLATE` is a smaller prompt change with its own
measurement.

**Power caveat:** as in the eleventh, only large differences show with
5–9 pairs. The gate condition rests on the few pairs whose round 1
stored it, 2 of 6 in the eleventh.

### Results (scored 2026-10-23)

10 samples, `coach_artifacts/measurement_round2_20261023_18*` and
`19*` (record IDs are UTC; fingerprint `87997863073facd8`). Every
sample reached round 2. 3 pairs were excluded because a round-2 reply
came from a retry (4ee454 in the v9 arm; d693ca and e52a94 in the v11
arm), which leaves 7 pairs. Neither trigger of the +5 rule fired: 7
pairs were compared, and 4 of them stored the gate in round 1. Hand
labels used the post-state at `8ffbf19`.

**Round 1, the fencing replication** (8 first attempts, 18 stored
blockers; 42ec47 and e52a94 are excluded as retries):
- the race: 11 blockers, in 5 runs;
- the in-flight gate: 6, in 3 runs (9ef325 #1 and #2, 8dc61a #1,
  802999 #1–#3);
- the deletion class: 0;
- other FPs: 1. 61e3c6 #2 says the `payloadHex` conversion can read past
  the 64-byte array, though `data_length` is a `uint8_t` documented as
  0–64, and says CAN-FD payloads exceed 64 bytes.

Valid: 17 of 18 (94%), at 2.25 blockers per run. 3 blockers were
evidence-demoted: 8dc61a #e1, a valid race claim whose quote joined
lines across a function boundary; 8dc61a #e2, a removal objection
quoting removed lines; and 61e3c6 #e1, a false lifetime claim. One was
hedge-demoted (9ef325 #h1, "may hide", about the removed decode call).

Against the eleventh's round 1 (race 10 of 10, other FPs 4, valid 80%)
this is quieter: the fence's 4 other FPs were not replicated. Over the
fence's 18 first-attempt round-1 runs so far: 43 stored blockers, 37
valid (86%), the race in 15 runs, the deletion class once (0.06 per
run), other FPs 5 (0.28 per run).

**Round 2** (7 pairs; origin tags confirmed by hand):

| | v11 arm | v9 arm |
|---|---|---|
| Stored blockers | 17 (2.43 per pair) | 16 (2.29 per pair) |
| Race, gate, FP | 10, 6, 1 | 9, 6, 1 |
| Carried, from-question, echo, new | 15, 2, 0, 0 | 16, 0, 0, 0 |
| Race kept, of the 4 pairs whose round 1 stored it | 4 | 4 |
| Gate kept, of the 4 pairs whose round 1 stored it | 3 | 3 |
| Round-1 FPs withdrawn (61e3c6 #2) | 0 of 1 | 0 of 1 |
| Valid share | 94% (16 of 17) | 94% (15 of 16) |
| Evidence- or hedge-demoted | 0 | 0 |
| First attempts that ran away (all 10 samples) | 2 | 1 |

**The gate, read by hand.** Each arm dropped it once, in different
pairs, and each time it became a question:
- **8dc61a:** round 1 stored the gate (R#1) and evidence-demoted a race
  blocker (#e1). The v11 arm's blockers are two race claims; the first
  is #e1 restated with a quote that passes. Its questions include "What
  is the intended backpressure strategy now that m_inFlightFrames
  tracking was removed?" The v9 arm kept the gate as two blockers and
  stated no race. This is the one pair the ship rule allows. The section
  told the reviewer the blocker stands unless the code contradicts it;
  the code does not, so moving it to a question is not what the
  instruction asked. It did keep the point visible.
- **42ec47:** round 1 stored the race (R#1) and the gate (R#2). The v11
  arm kept both. The v9 arm's blockers are three race claims, and its
  questions ask whether the backpressure change "should … be restored".

**The two from-question blockers** are 8dc61a's race claims above, both
valid. v9's feedback carries no reviewer questions, so that arm never
saw the demoted claim. This is the first recorded case of round 2
recovering a valid blocker the evidence check demoted. The same channel
could return a demoted false positive; none did here.

**Runaways.** The tails of two of the three end the same way. The v9
arm's (4ee454): "…So this is not an issue. Now let me also check if
there are any other issues." The v11 arm's (e52a94): "Now let me also
check if there are any other issues: 1. The removal of signal batching
… 2. The removal of `forceFrameCountForTesting`…". The third (v11,
d693ca) is prose about the deleted test file. So the open-ended search
is not caused by the section, and v11's "do not search the diff again
to re-confirm it" did not stop it. In the compared pairs the two arms'
thinking is of a size, 2.8–6.7K chars against 2.7–9.4K.

**Round 1 ran away too:** the reviewer's first attempt in 42ec47 and
e52a94, against 0 of 10 in the eleventh. In e52a94 the retry ran away as
well, the first retry on record that did not recover; the second retry
did. The engineer did not run away.

| Metric | Predicted | Observed | Outcome |
|---|---|---|---|
| Round-2 first attempts that ran away | ≤ the v9 arm's + 1 | 2 against 1 | HIT, at the limit |
| Gate kept where the v9 arm keeps it | every pair | 2 of 3 (8dc61a, asked as a question) | MISSED; within the ship rule's allowance |
| Race kept | ≥ the v9 arm's − 1 | 4 and 4 of 4 | HIT |
| Round-1 FPs withdrawn | ≥ the v9 arm's − 1 | 0 and 0 of 1 | HIT |
| Echo and from-question FPs | ≤ the v9 arm's + 1 | 0 and 0 | HIT |
| Valid share, round 2 | both ≥ 80%; v11 ≥ v9 − 10 | 94% and 94% | HIT |
| Round-2 blockers per pair | ≤ the v9 arm's + 0.5 | 2.43 against 2.29 | HIT |
| Round 1 | deletion ≤ 0.2, race in ≥ 3 runs, valid ≥ 70% | 0, 5 of 8, 94%; other FPs 0.13 per run | HIT |

**By the recorded rule: ship.** Every condition holds. The two that
sank v10 hold at their limits: runaways 2 against 1, and the gate
dropped once where the v9 arm kept it, read above. The arms are even on
the gate (3 of 4 each), and the eleventh's two costs did not repeat as
costs: the gate survived the section, and the runaway tails show the
same search in both arms.

### Amendment (2026-10-23): shipped as v11.1

The rule's verdict stands: PROMPT_VERSION `v11.1-critiques-feedback`.
From round 2 on a debate sends the previous round's replies in the
CRITIQUES section after the code: every channel but reviewer nits,
engineer blockers included, the last round only. The proposal stays the
author's text, so `inputs.proposal` now equals
`inputs.original_proposal`. Round 1 is unchanged byte for byte, so
round-1 samples and the golden suite compare across the change. A
debate's round 2 is the pair measurement's critiques arm, pinned
identical by a test, so the twelfth's samples are the shipped format's
own. The pair measurement keeps v9's feedback as its comparison arm.

Fingerprints: debates and round-1 measurements move from
`30f7aeff90e8ec76` to `8e76794ac4946aab`, since their templates now
include the section and no longer v9's feedback; pair records stay at
`87997863073facd8`. Fake-driven runs on the bridge fixture send
byte-identical round-1 requests before and after, and identical pair
requests; a debate's rounds 2 and 3 differ as designed, and its record
also differs in `inputs.proposal`.

The section's measured benefit on this fixture was one recovered
blocker; the rest is protocol, feedback no longer reading as the
author's text. Round-2 runaways in live debates are the number to
watch (STATUS #16). Backlog #11 is closed.

## Thirteenth Measurement — Offline Replay of Judge Variants

*Design and prediction recorded 2026-10-23, before any variant was
scored. The replay tool, the labels and the reproduction check below
were built and run first; no variant's numbers had been printed.*

**Why:** the three changes most likely to raise precision further are
deterministic. They can be scored on archived replies without a model
call, before any live run. This is the first step of a roadmap: score
the variants here, measure the survivors on a corpus of triaged diffs
(backlog #7), and only then change debates.

**Tool:** `python -m eval_harness.replay` (no model). It rebuilds each
round-1 reply's raw blockers: the stored ones, plus those the evidence
and hedge checks demoted, recovered from the end of its questions. It
then re-judges them under each variant. Hand labels per blocker are in
`eval_harness/labels.json`, transcribed from the tenth, eleventh and
twelfth measurements. 10 demoted items that the ADR never classified
are labelled by hand and marked as such.

**Reproduction check (done):** re-applying the current judge to all 84
raw blockers of the 28 first-attempt samples reproduces every record's
stored split exactly, including G3's, which ran under j4.

**Samples:** first attempts on the bridge fixture: G3 (10), the
eleventh's round 1 (10) and the twelfth's round 1 (8). All have quoted
blockers and the post-change evidence check. The sixth (v6, no quotes)
is left out.

**Variants**, each on top of the current evidence and hedge checks:
- **gapped:** a quote's lines may skip post-change lines, in order,
  within one hunk. Target: the 3 valid race blockers demoted because
  their quotes skipped lines (2f2843 #e1, 5ef90b #e1, 8dc61a #e1).
- **linked:** a blocker is demoted when its claim names code
  identifiers (`retrieval.code_like`) and none of them occurs anywhere
  in the hunk its quote matched (removed lines and the hunk header
  included). A claim that names none passes. Target: real quotes that do
  not support the claim (55c897 #1, c55779 #4).
- **gapped+linked.**
- **vote k-of-n @variant:** a review is n samples, each judged by the
  variant. Two blockers are linked when their quotes matched a shared
  post-change line of 8 or more non-space characters. A group of linked
  blockers is kept when it spans at least k samples. Scored on every
  3-subset of each set, with k = 2. Cost: n reviewer round-1 calls per
  debate.

**Metrics, per review** (a single sample, or one 3-subset when voting):
blockers, the valid share (race or gate), FP blockers (deletion,
removal objection, other), and whether the race and the gate are among
the kept blockers. Results are pooled over the three sets and given per
set.

**Baseline, the current judge on single samples** (pooled; from the
recorded labels): 2.18 blockers per review, 89% valid (54 of 61), 0.25
FPs per review, race found 0.79, gate found 0.29.

**Prediction:**

| Variant | FPs per review | Race found | Gate found | Valid blockers demoted |
|---|---|---|---|---|
| gapped | 0.25–0.29 (0–1 readmitted) | 0.79–0.83 | 0.29 | — (3 readmitted) |
| linked | 0.15–0.22 | ≥ 0.75 | ≥ 0.25 | 0–1 |
| vote 2-of-3 @j7 | 0.05–0.15 | 0.75–0.90 | 0.30–0.50 | — |

Reasons: most false positives quote a line that no other sample quotes,
while the race recurs. Gate blockers that quote the backpressure check
are linked to the race's group. Under voting, 6e7367 #1 is the
expected surviving FP: it quotes `++m_currentFrameCount;` like the race
blockers.

**Rule:** a variant passes if, pooled, FPs per review fall and both
race-found and gate-found drop by at most 0.1 against the baseline. A
passing variant becomes a candidate to measure on the corpus (#7).
Nothing changes in debates on the replay alone.

**Limits:**
- **Dev data.** The labels, and the variants' design, come from people
  who had read these replies, and the records come from one fixture. The
  replay can rule a variant out, or make it a candidate; it cannot ship
  one.
- **Demotions are recovered, not observed:** the tail of `questions`,
  as the scorers read it.
- **Voting's recall comparison** sets three samples against one. The
  same table at k = 1 (the union of three samples, no vote) is reported
  as a reference.

### Results (scored 2026-10-23)

Pooled over the 28 samples (296 voted reviews: every 3-subset of each
set):

| Variant | Blockers per review | Valid | FPs per review | Race found | Gate found |
|---|---|---|---|---|---|
| current judge (j7) | 2.18 | 89% | 0.25 | 0.79 | 0.29 |
| gapped | 2.29 | 89% | 0.25 | 0.82 | 0.29 |
| linked | 2.11 | 92% | 0.18 | 0.79 | 0.29 |
| gapped+linked | 2.21 | 92% | 0.18 | 0.82 | 0.29 |
| vote 2-of-3 @j7 | 4.48 | 96% | 0.16 | 0.92 | 0.47 |
| vote 2-of-3 @gapped+linked | 4.85 | 97% | 0.16 | 0.93 | 0.47 |
| reference: union of 3, no vote @j7 | 6.51 | 88% | 0.80 | 0.99 | 0.66 |

**What each variant changed, blocker by blocker:**
- **gapped** readmitted exactly its three targets, all valid race
  blockers (2f2843 #e1, 5ef90b #e1, 8dc61a #e1), and nothing else. Of
  the other 13 evidence-demoted blockers, no quote matched even with
  gaps, since they quote removed lines or code that does not exist.
- **linked** demoted exactly its two targets, both deletion-class FPs
  (55c897 #1, c55779 #4), and no valid blocker. It also catches 9ef325
  #h1, which hedging demoted anyway.
- **vote** removed 5 of the 7 FPs kept by the current judge. Two survive
  in the subsets where their group recurs:
  - 6e7367 #1 (26 of 120 subsets), as predicted. It quotes
    `++m_currentFrameCount;` like the race blockers.
  - 61e3c6 #2 (21 of 56). The same reply's race blocker quoted 14 lines
    of `handleFrameInternal`, the `payloadHex` line included, and that
    linked the false "buffer overflow" claim to the race's group. So a
    long quote can carry an unrelated claim through the vote. In the
    twelfth's set this raised FPs per review from 0.12 to 0.38.
- A voted review keeps every member of a kept group, so it repeats
  blockers across samples, at 4.5–4.9 per review. A debate would show
  one per group.

| Prediction | Predicted | Observed | Outcome |
|---|---|---|---|
| gapped: FPs per review | 0.25–0.29 | 0.25 (0 readmitted) | HIT |
| gapped: race found | 0.79–0.83 | 0.82 | HIT |
| linked: FPs per review | 0.15–0.22 | 0.18 | HIT |
| linked: valid blockers demoted | 0–1 | 0 | HIT |
| linked: race, gate found | ≥ 0.75, ≥ 0.25 | 0.79, 0.29 | HIT |
| vote 2-of-3: FPs per review | 0.05–0.15 | 0.16 | MISSED HIGH |
| vote 2-of-3: race found | 0.75–0.90 | 0.92 | MISSED HIGH |
| vote 2-of-3: gate found | 0.30–0.50 | 0.47 | HIT |

**By the rule** (FPs fall; race and gate each drop by at most 0.1):
- **linked, gapped+linked, and voting over either: pass.** They become
  candidates for the corpus.
- **gapped alone: does not pass.** Its FPs do not fall; it is a recall
  fix with no false-positive cost on this data. It is carried as part
  of gapped+linked.

**Reading:**
- **The single-sample judge has room for two cheap fixes, at no model
  cost.** gapped+linked takes the stored valid share from 89% to 92%
  and race-found from 0.79 to 0.82.
- **Voting is the larger lever.** Against the union of the same three
  samples it cuts FPs per review from 0.80 to 0.16 and keeps most of the
  recall: race 0.99 → 0.92, gate 0.66 → 0.47. Against today's single
  sample it is better on all three counts, at three times the
  reviewer's round-1 calls.
- **Its weak point is the bridge a long quote makes.** One fix is to
  link on each blocker's first quoted line only. Choosing it here would
  be tuning on these data, so it is left as a variant to pre-register
  for the corpus.
- **None of this ships from the replay.** The corpus measurement decides
  (ADR-0002's next measurement; backlog #7).

## Fourteenth Measurement — Corpus Baseline (backlog #7)

**Status (2026-10-23): the set was approved as listed, with the
`--no-llm` indexes and the fixtures' file sets unchanged, sampled the
same evening and scored (Results, below).** Everything so far was measured
on one fixture, the bridge refactor, which has two known bugs. The
corpus is the first test of whether its numbers travel.

### Fixtures

`docs/fixtures/corpus.json` describes seven real QtTune diffs, in
`docs/fixtures/corpus/<id>/change.diff`, each with the index of its own
base (`repo_context.json` beside it, built with `--no-llm` from a
throwaway clone, so the pack's purposes come from each file's first
prose comment rather than a model). Tests, docs and `*.md` are excluded
from every diff. Proposals are written in the diff's real direction
(backlog #21), as an author would describe the change, without naming
the bug.

Five **bug fixtures** are the reverse of a fix commit (`git diff <fix>
<fix>^`), so the diff introduces the bugs the commit fixed. Their known
bugs come from the commit's message and diff:

| fixture | fix commit | layer | chars | known bugs |
|---|---|---|---|---|
| `backoff_clamp_d1c20c0` | d1c20c0, clamp backoff step to the 5 s cap | core | 4.0K | the doubled wait overshoots the cap (3200 → 6400 ms) |
| `trusted_count_6420f09` | 6420f09, ignore vendor counts under hard-error statuses | core | 3.4K | count trusted under an error status; the surrogate's static batch replays stale frames |
| `poll_override_90020bd` | 90020bd, `?poll=` overrides the rotation | app (QML first; the code is core) | 6.7K | `?poll=` ignored under a mux profile; `?poll=` without `?filter=` rejected at parse |
| `connect_start_4a86231` | 4a86231, start sessions on the GUI thread | bridge | 7.9K | session started off-thread before the GUI owns it (freed `this` under a running worker); unsubscribed rows stop updating |
| `decode_length_b47687c` | b47687c, honor payload length in decode | bridge | 11.2K | decode length hardcoded to 8; staging buffer cleared per frame; drops unreported while saturated; payload length unclamped |

Two **clean fixtures** are forward diffs of commits that nothing later
fixed at the time of writing, for a false-positive rate:
`init_noops_cf03331` (refactor: `ecuio_init` and `ecuio_shutdown`
become optional no-ops; ten files across app, QML and core, 10.1K) and
`ecu_support_7d297b4` (feature: log what each ECU supports; bridge,
7.6K). "Clean" is a presumption: a found bug would be a finding, not a
false positive, and would move the fixture to the bug set.

Rejected candidates: `105e2cb` (68K, over the input limit even without
tests), `5924214` (its added comments name the bug as a known issue),
`046b320` (a header whose removed lines state the correct constants).

**Known costs, recorded before sampling:**
- **Leak.** The removed lines of a reverse diff carry the fix's own
  comments, which name the bug. The reviewer reads them. A quote must
  come from post-change lines, so a blocker quoting a removed comment is
  demoted, but its claim may be informed by it. The manifest's `leak`
  field says what each fixture reveals. Recall on these fixtures is
  therefore an upper bound; a forward fixture from the bug-introducing
  commit would be the honest form, and is the next build if the leak
  shows in the claims.
- **`decode_length_b47687c` reviews the bridge fixture's file,** three
  commits after its base, so it is not independent of the one fixture
  measured so far.
- **Layer notes follow the first file** (#8): `poll_override_90020bd`
  gets the app note although its bugs are in core.
- **Symbol-matched recall is a pointer.** The scorer credits a bug when
  a stored blocker's claim names one of its symbols; the claim must be
  read before the bug counts as found.

### Design

- 5 round-1 reviewer samples per fixture, 35 calls, through
  `python -m eval_harness.corpus run --fixture all --runs 5` (about 2–3
  h of GPU). Round 1 only, as in every measurement since the fifth.
- Prompt v11.1, judge j7, the debate fingerprint. First attempts only;
  retries are excluded as before.
- Scored by `eval_harness.corpus score`, then read by hand: each stored
  blocker labelled valid (a known bug, or a real finding) or a false
  positive, with the class.

### Predictions (recorded 2026-10-23, before any sample)

The bridge fixture gave 80–94% valid stored blockers and found the race
in 10 of 10 runs, the gate in 2–4 of 10. The corpus is unfamiliar code
in smaller diffs, with the leak working in recall's favour.

| metric | prediction |
|---|---|
| stored blockers per run, bug fixtures | 1.5–3.0 |
| stored blockers per run, clean fixtures | 0.5–1.5 |
| valid share of stored blockers, pooled | 60–80% |
| `backoff_overshoot` found | 3–5 of 5 (arithmetic, visible, leaked) |
| `count_under_error` found | 1–3 of 5; `static_batch_replay` 0–2 |
| `poll_ignored` found | 2–4 of 5; `poll_needs_filter_at_parse` 0–2 |
| `start_before_gui_owns` found | 3–5 of 5 (thread safety, the reviewer's strongest class) |
| `unsubscribed_rows_freeze` found | 1–3 of 5 |
| `decode_length_8` found | 3–5 of 5; `staging_clear_per_frame` 2–4; `drops_unreported_when_saturated` 1–3; `payload_length_unclamped` 1–3 |
| evidence demotions per run | 0.2–0.6, higher than the bridge's: smaller diffs leave fewer quotable lines |
| first attempts that run away | 1–4 of 35 |

**What the baseline decides:** nothing ships from it. It fixes the
corpus numbers the replay's candidates (gapped quotes with claim–quote
linkage; 2-of-3 voting, with the first-line-only link pre-registered
here as its variant) are measured against next, with the thirteenth
measurement's rule: FPs fall, and no known bug's recall drops by more
than 0.1 pooled over the bug fixtures. If the leak shows in the claims
(blockers that restate a removed comment), the next build replaces the
affected fixture with a forward diff from the bug-introducing commit.

### Results (scored 2026-10-23)

35 samples in 55 minutes, records
`coach_artifacts/measurement_round1_20261024_015410_fa2343.json` to
`..._024702_0019d0.json` (record IDs are UTC). Two first attempts ran
away and were retried, one on `decode_length_b47687c` and one on
`init_noops_cf03331`; both are excluded, as retries always are, which
leaves 33 scored runs. Every scored run is a first attempt.

The records carry three prompt fingerprints, one per layer note: app
`45cc2b200fa76e7a`, bridge `8e76794ac4946aab` (the bridge fixture's own)
and core `b7a37ffc88eed510`. The layer note is a template the
fingerprint hashes, so this is the design, not mixed arms; the scorer
now warns only when one fixture's records differ.

**Labels.** Every item, stored or demoted, was read against its
fixture's `post_rev` and labelled in `eval_harness/corpus_labels.json`
(`python -m eval_harness.corpus score` prints them). Two notes decide
most of the false positives:
- In `poll_override_90020bd`'s post-state, `parse_query` rejects
  `?poll=` without `?filter=`, and `resolve_channels` then builds
  exactly one channel from the filter. Every claim of a missing channel
  check for poll mode is false: another function enforces the
  invariant.
- In `ecu_support_7d297b4`, `ecuio_dropped_request_t.request` is
  `uint8_t[3]` and the struct is value-initialized, so `request[0]` is in
  bounds; both functions said to race run on the GUI thread.

The symbol match of the scorer was a poor proxy: it credited
`poll_ignored` in 5 of 5 runs, the labels in 1 of 5, because the
invariant-elsewhere claims name `poll_pid`. The labels supersede it.

| fixture | runs | stored | valid | FP | evidence-demoted (valid) | hedge-demoted (valid) |
|---|---|---|---|---|---|---|
| backoff_clamp_d1c20c0 | 5 | 4 | 4 | 0 | 0 | 0 |
| trusted_count_6420f09 | 5 | 3 | 3 | 0 | 8 (7) | 1 (1) |
| poll_override_90020bd | 5 | 11 | 2 | 9 | 0 | 2 (1) |
| connect_start_4a86231 | 5 | 5 | 3 | 2 | 8 (7) | 1 (1) |
| decode_length_b47687c | 4 | 15 | 12 | 3 | 0 | 0 |
| init_noops_cf03331 (clean) | 4 | 0 | 0 | 0 | 0 | 0 |
| ecu_support_7d297b4 (clean) | 5 | 4 | 0 | 4 | 1 (0) | 4 (0) |
| **pooled** | 33 | 42 | 24 | 18 | 17 (14) | 8 (3) |

Valid includes 2 `unlisted` items in `decode_length_b47687c`: the typed
`setSignalSet` parameter, which the fix commit reverted as a FIX but
which is not a functional bug. Without them, 22 of 42 are valid.

False positives by class: invariant-elsewhere 8 (all in
`poll_override_90020bd`), thread-confusion 3, bounds-fixed-array 3 (all
in `ecu_support_7d297b4`), other 3, deletion 1.

Recall per known bug, as runs with a stored blocker, and as runs with
any item about it, stored or demoted (what the reviewer said before the
guardrails):

| known bug | predicted | stored | any item | |
|---|---|---|---|---|
| backoff_overshoot | 3–5 of 5 | 4/5 | 4/5 | HIT |
| count_under_error | 1–3 of 5 | 2/5 | 5/5 | HIT |
| static_batch_replay | 0–2 of 5 | 2/5 | 5/5 | HIT |
| poll_ignored | 2–4 of 5 | 1/5 | 1/5 | MISSED LOW |
| poll_needs_filter_at_parse | 0–2 of 5 | 1/5 | 2/5 | HIT |
| start_before_gui_owns | 3–5 of 5 | 2/5 | 5/5 | MISSED LOW |
| unsubscribed_rows_freeze | 1–3 of 5 | 1/5 | 1/5 | HIT |
| decode_length_8 | 0.6–1.0 per run | 4/4 | 4/4 | HIT |
| staging_clear_per_frame | 0.4–0.8 | 3/4 | 3/4 | HIT |
| drops_unreported_when_saturated | 0.2–0.6 | 3/4 | 3/4 | MISSED HIGH |
| payload_length_unclamped | 0.2–0.6 | 0/4 | 0/4 | MISSED LOW |

Mean recall per bug: 0.46 stored, 0.65 for any item.

| metric | predicted | observed | |
|---|---|---|---|
| stored blockers per run, bug fixtures | 1.5–3.0 | 1.58 (38 in 24 runs) | HIT |
| stored blockers per run, clean fixtures | 0.5–1.5 | 0.44 (4 in 9 runs) | MISSED LOW |
| valid share of stored blockers, pooled | 60–80% | 57% (24 of 42) | MISSED LOW |
| evidence demotions per run | 0.2–0.6 | 0.52 | HIT |
| first attempts that run away | 1–4 of 35 | 2 | HIT |

**Reading:**
- **The bridge fixture's precision did not travel whole.** 57% valid
  against 80–94% there. One fixture carries half the false positives:
  `poll_override_90020bd`'s 8 invariant-elsewhere blockers, a class the
  bridge fixture never showed. The reviewer reads a removed backstop in
  one function and does not see that another function, in the same
  file, enforces the invariant. Without that fixture, 22 of 31 stored
  blockers are valid (71%).
- **On these diffs the evidence check costs more than it saves.** It
  demoted 17 items: 14 valid, 3 false. On the bridge fixture it was the
  main false-positive fix, because there the false class was claims
  about removed code. Here the bugs are removals: the change deletes a
  safety check, and the reviewer quotes the deleted check. That moved
  `count_under_error`, `static_batch_replay` and `start_before_gui_owns`
  from 5 of 5 runs to 2 of 5. This is the cost j4 recorded when it
  shipped ("removal-caused defects must stay quotable"), now measured.
  It is quotable: 6792a6 #1 and cab81e #1 quote the post-change line
  that now misbehaves, and are stored.
- **The leak is real but narrow.** In `trusted_count_6420f09`, four
  claims cite the removed comments outright ("the surrogate comment
  explicitly warns…"), and those claims are among the demoted ones. The
  other bug fixtures' valid claims do not lean on removed comments;
  `backoff_clamp`'s compare the inlined code with the removed function,
  which is ordinary diff reading.
- **Clean diffs are cheap where the code is straightforward.**
  `init_noops_cf03331` drew no blocker in four runs, ten files and all.
  `ecu_support_7d297b4` drew one per run, all false.
- **Recurring false positives undercut voting.** bounds-fixed-array
  recurs in 3 of 5 `ecu_support` runs, and invariant-elsewhere in 5 of
  5 `poll_override` runs, so 2-of-3 voting would keep both. On the
  bridge fixture most false positives appeared once. The replay's
  voting result is therefore not expected to transfer as measured; this
  is a prediction to record before the corpus replay, not a result.
- **The symbol scorer is a triage aid only.** It over-credited one bug
  five-fold and missed paraphrased claims ("the cap condition is
  wrong"). Corpus numbers come from the labels.

**What this decides:** nothing ships from a baseline. It sets the
numbers the next measurements are compared with, on this corpus, with
these labels:
1. **The replay's candidates, offline:** gapped quotes with claim–quote
   linkage, and 2-of-3 voting (with the first-line-only link
   pre-registered in the thirteenth measurement), replayed over these
   33 runs and scored with `corpus_labels.json`. No GPU. The rule stays:
   false positives fall, and no known bug's recall drops by more than 0.1
   pooled.
2. **Removal-caused defects:** the largest recall loss is the evidence
   check's. Options to weigh, each predicted before measuring: a prompt
   change telling the reviewer to quote the post-change line a removal
   breaks, which keeps j4 as it is; or a judge change that accepts a
   removed-line quote for a claim that the removal itself is the defect,
   which risks readmitting the bridge fixture's deletion class.
3. **Invariant-elsewhere:** a recall-side lever (more of the same file in
   the pack, or the function that enforces the invariant) is a pack
   change with its own PACK_FORMAT_VERSION.

## Fifteenth Measurement — Corpus Replay and a Removed-Line Exception

**Status (2026-10-23): registered before any variant was scored, then
scored the same night (Results, below).** Before registering, only
the sanity check has run: j7 reproduces every stored split, 28 bridge
samples and 33 corpus samples.

**Why now.** The fourteenth left two questions that the archived replies
can answer with no model call:
- **Does voting survive correlated faults?** The thirteenth's voting gain
  came from false positives that appeared once. On the corpus,
  invariant-elsewhere recurs in 5 of 5 `poll_override` runs and
  bounds-fixed-array in 3 of 5 `ecu_support` runs.
- **Can the removal-caused recall loss be fixed in the judge?** The
  evidence check demoted 14 valid items on the corpus, all quoting
  removed lines. The reviewer prompt has said since v9 to quote "the code
  after the change that the removal leaves broken or unprotected", and
  the corpus reviewer quoted removed lines anyway, so a stronger prompt
  has weak prior odds. A judge exception is cheap to replay, and its
  risk, readmitting the bridge fixture's deletion and removal-objection
  classes, can be measured on the bridge records it would affect.

**Variants** (`eval_harness/replay.py`, `--corpus` for the corpus):
- the thirteenth's: j7, gapped, linked, gapped+linked, and 2-of-3 voting
  over each;
- **removed:** a quote the evidence check rejects is accepted when it is
  found in the named file's code as it read before the change (context
  and removed lines, same matching rules);
- **removed+linked:** removed, with claim–quote linkage on every quote,
  pre-change ones included;
- **removed+said:** removed, but a pre-change quote is accepted only when
  the claim names a removal (`remov…`, `delet…`, `no longer`, `dropp…`,
  `eliminat…`). The word list was fixed here, after reading the corpus
  claims, so this variant is partly tuned on the corpus; the bridge
  records are its test.

Votes are counted as in the thirteenth: every kept member counts, so a
blocker that recurs is counted once per sample it appears in.

**Data:** corpus, the fourteenth's 33 runs with `corpus_labels.json`;
bridge, the thirteenth's 28 samples with `labels.json` (glob
`measurement_round1_20261023_01*`, `measurement_round2_20261023_*`).

**Rules, recorded before scoring:**
- **Precision variants** (gapped, linked, gapped+linked, voting) become
  candidates for a live measurement if, on the corpus, FPs per review
  fall and mean recall per known bug drops by at most 0.1.
- **Exception variants** become candidates if all three hold: corpus mean
  recall rises by at least 0.10; corpus FPs per review rise by at most
  0.05; bridge FPs per review rise by at most 0.05, with race and gate
  found dropping by at most 0.1. The bridge's readmitted false positives
  are reported by class: removal objections there are partly an
  artifact of its mismatched proposal (backlog #21), deletion claims are
  not.

**Baselines (j7):** corpus 57% valid, 0.55 FPs per review, mean recall
0.46, 0.44 FPs per clean review. Bridge 0.25 FPs per review, race 0.79,
gate 0.29.

**Predictions:**

| variant | data | metric | prediction |
|---|---|---|---|
| gapped | corpus | FPs per review | 0.52–0.58 |
| gapped | corpus | mean recall | 0.46–0.50 |
| linked, gapped+linked | corpus | FPs per review | 0.48–0.55 (0–2 FPs demoted) |
| linked, gapped+linked | corpus | mean recall | 0.40–0.46 |
| vote 2-of-3 @j7 | corpus | FPs per review | 0.60–1.20, not below j7 |
| vote 2-of-3 @j7 | corpus | mean recall | 0.40–0.55 |
| removed | corpus | mean recall | 0.58–0.65 |
| removed | corpus | FPs per review | 0.58–0.64 |
| removed | corpus | valid share | 62–68% |
| removed+linked | corpus | all three | within 0.03 (3 points) of removed |
| removed+said | corpus | mean recall | 0.58–0.65 |
| removed+said | corpus | FPs per review | 0.56–0.62 |
| removed | bridge | FPs per review | 0.45–0.80 |
| removed | bridge | race, gate found | race 0.79–0.85, gate 0.35–0.55 |
| removed+linked | bridge | FPs per review | 0.40–0.75 |
| removed+said | bridge | FPs per review | 0.35–0.65 |

**Expected by the rules:** no precision variant passes on the corpus
(linkage demotes too few, voting keeps the recurring faults). No
exception variant passes: each fails the bridge condition, through
removal objections and deletion claims that quote removed lines. If so,
the removal-caused loss is not a judge problem that a quote rule can
solve, because the judge cannot tell a removal the change intends from
a removal that breaks something; that takes a reader of intent, so the
next lever is a measured prompt or protocol change.

### Results (scored 2026-10-23)

`python -m eval_harness.replay --corpus "coach_artifacts/measurement_round1_20261024_0[12]*.json"`
and the thirteenth's bridge command. j7 reproduced every stored split
on both, and the bridge's j7, gapped, linked and voting rows equal the
thirteenth's.

| variant | corpus valid | corpus FP/rev | corpus recall | clean FP/rev | bridge FP/rev | bridge race, gate |
|---|---|---|---|---|---|---|
| j7 | 57% | 0.55 | 0.46 | 0.44 | 0.25 | 0.79, 0.29 |
| gapped | 57% | 0.55 | 0.46 | 0.44 | 0.25 | 0.82, 0.29 |
| linked | 59% | 0.48 | 0.44 | 0.44 | 0.18 | 0.79, 0.29 |
| gapped+linked | 59% | 0.48 | 0.44 | 0.44 | 0.18 | 0.82, 0.29 |
| vote 2-of-3 @j7 | 58% | 0.98 | 0.53 | 1.07 | 0.16 | 0.92, 0.47 |
| vote 2-of-3 @linked | 64% | 0.72 | 0.48 | 1.07 | 0.16 | 0.92, 0.47 |
| removed | 62% | 0.61 | 0.59 | 0.44 | 0.50 | 0.79, 0.29 |
| removed+linked | 62% | 0.55 | 0.53 | 0.44 | 0.39 | 0.79, 0.29 |
| removed+said | 61% | 0.58 | 0.57 | 0.44 | 0.36 | 0.79, 0.29 |

| prediction | predicted | observed | |
|---|---|---|---|
| gapped, corpus FPs per review | 0.52–0.58 | 0.55 | HIT |
| gapped, corpus mean recall | 0.46–0.50 | 0.46 | HIT |
| linked, corpus FPs per review | 0.48–0.55 | 0.48 | HIT |
| linked, corpus mean recall | 0.40–0.46 | 0.44 | HIT |
| vote @j7, corpus FPs per review | 0.60–1.20 | 0.98 | HIT |
| vote @j7, corpus mean recall | 0.40–0.55 | 0.53 | HIT |
| removed, corpus mean recall | 0.58–0.65 | 0.59 | HIT |
| removed, corpus FPs per review | 0.58–0.64 | 0.61 | HIT |
| removed, corpus valid share | 62–68% | 62% | HIT |
| removed+linked within 0.03 of removed | — | recall 0.06 and FPs 0.06 lower | MISSED |
| removed+said, corpus mean recall | 0.58–0.65 | 0.57 | MISSED LOW |
| removed+said, corpus FPs per review | 0.56–0.62 | 0.58 | HIT |
| removed, bridge FPs per review | 0.45–0.80 | 0.50 | HIT |
| removed, bridge race / gate | 0.79–0.85 / 0.35–0.55 | 0.79 / 0.29 | HIT / MISSED LOW |
| removed+linked, bridge FPs per review | 0.40–0.75 | 0.39 | MISSED LOW |
| removed+said, bridge FPs per review | 0.35–0.65 | 0.36 | HIT |
| no precision variant passes | — | linked passes | MISSED |
| no exception variant passes | — | none passes | HIT |

**By the rules:**
- **linked and gapped+linked pass on the corpus:** FPs per review 0.55
  → 0.48, mean recall 0.46 → 0.44. With the thirteenth's bridge pass,
  claim–quote linkage is now a candidate on both data sets.
- **gapped** changes nothing on the corpus: none of its demoted quotes
  skip lines. It stays a bridge-only recall fix.
- **Voting fails.** FPs per review rise from 0.55 to 0.98, and on clean
  fixtures from 0.44 to 1.07. The recurring faults the fourteenth
  pointed at are kept, and counted once per sample they recur in.
- **No exception passes.** removed fails the corpus FP limit (+0.06)
  and the bridge (+0.25). removed+linked fails corpus recall (+0.07)
  and the bridge (+0.14). removed+said meets both corpus conditions
  (recall +0.11, FPs +0.03) and fails the bridge (+0.11).

**What the variants changed:**
- **The exception can readmit at most 9 of the 14 valid demotions,**
  not 14. Only 9 quote code that exists before the change; the other 5
  quote text found on neither side as written (comment blocks re-flowed,
  lines joined). The fourteenth's reading that all 14 quoted removed
  lines overstated it.
- **removed readmits 4 deletion claims on the bridge,** with 3 removal
  objections and 2 deleted-test objections. That is the risk the
  exception was registered against, measured.
- **removed+said readmits no deletion claim on the bridge.** Its whole
  bridge rise is 3 removal objections and the 2 deleted-test items.
  Removal objections on the bridge fixture are partly the artifact of
  its mismatched proposal (#21); the rule was registered without an
  exception for them, so the variant fails as registered.
- **Linkage is half accident on the corpus.** Of its 4 corpus
  demotions, 2 turn on all-caps words that `code_like` counts as
  identifiers: `PID` demoted an invariant-elsewhere FP, `UI` demoted a
  valid `drops_unreported_when_saturated` blocker. The other 2 are the
  intended signal: claims resting on `chan_count`, which the quoted
  hunk never touches.

**Reading:**
- **Same-model voting is ruled out on the evidence.** Redundancy needs
  independent faults; the corpus shows they are not. Diversity (another
  model or another prompt) is the remaining form of redundancy, and it
  needs live samples.
- **The removal-caused loss is mostly not a quote-matching problem.**
  At best a judge exception recovers 9 of 14, and the safest gate tried
  (removal words) still readmits removal objections, which a judge that
  reads no intent cannot tell from harmful removals.
- **These 61 samples have now chosen variants twice.** Anything picked
  from them needs fresh samples before it ships: a held-out corpus run,
  labelled before any variant is applied to it.

**Open choices (not decided here):**
1. Measure linkage live as a judge change (JUDGE_VERSION bump), as is
   or with bare all-caps words excluded from its identifiers; the second
   is a new variant and needs registering first.
2. For removed+said: accept the rule's result, or fix #21 first (bridge
   samples with a proposal in the diff's real direction) and judge the
   exception on removal objections without the artifact.
3. Collect a held-out corpus sample (35 runs, about an hour of GPU) and
   score the surviving candidates on it.

### Amendment (2026-10-23): filtered linkage and a composed arm

Registered after the results above and before replaying either variant.

**Filtered linkage (flinked).** `retrieval.code_like` counts any token
with an uppercase letter after its first character as code, so the
acronyms `PID` and `UI` were read as identifiers and decided 2 of
linkage's 4 corpus demotions. The rule is defined on principle, not on
those two cases: an acronym is a token of capital letters only, with no
digit, underscore or lowercase letter. For linkage it counts as a code
identifier only when the review's index defines it as a type or
constant name. `SCONFIG`, a typedef in the core indexes, is the kind of
all-caps name the escape keeps; the corpus has no other all-caps type
or constant without an underscore. Tokens with digits (`J2534`) and
mixed case are unchanged. Variants: flinked, gapped+flinked.

**Composed arm (removed+said+flinked).** The removal-word exception
(recall) with filtered linkage on every quote (precision); they address
disjoint failures.

**Retrieval audit.** The same `code_like` feeds one place in retrieval:
the removed-only identifiers that mark or omit pack entries. Across the
bridge fixture and the seven corpus fixtures, one pack is affected:
`decode_length_b47687c` marks a purpose as naming removed-only
identifiers `FIX, ID`, words from a removed comment. The mark itself is
right (the purpose is the removed comment), the names are not. No
entry is omitted because of an acronym, and the bridge pack is
unaffected. Changing it changes what the models see, so it is a pack
change with PACK_FORMAT_VERSION and PROMPT_VERSION bumps and its own
measurement; it is recorded here, not fixed.

**Rules:** as above; flinked and gapped+flinked are precision variants,
the composed arm is an exception variant.

| variant | data | metric | prediction |
|---|---|---|---|
| flinked, gapped+flinked | corpus | FPs per review | 0.48–0.55 |
| flinked, gapped+flinked | corpus | mean recall | 0.44–0.47 |
| flinked | bridge | FPs per review; race, gate | 0.18–0.21; 0.79, 0.29 |
| removed+said+flinked | corpus | FPs per review | 0.50–0.58 |
| removed+said+flinked | corpus | mean recall | 0.55–0.58 |
| removed+said+flinked | bridge | FPs per review | 0.29–0.33 |

**Expected by the rules:** flinked passes on both data sets. The
composed arm is borderline on two conditions, corpus recall (+0.09 to
+0.12) and bridge FPs (+0.04 to +0.08); predicted to pass both,
narrowly.

**Amendment results (scored 2026-10-23):**

| variant | corpus valid | corpus FP/rev | corpus recall | bridge FP/rev | bridge race, gate |
|---|---|---|---|---|---|
| j7 | 57% | 0.545 | 0.464 | 0.25 | 0.79, 0.29 |
| flinked | 59% | 0.515 | 0.464 | 0.18 | 0.79, 0.29 |
| gapped+flinked | 59% | 0.515 | 0.464 | 0.18 | 0.82, 0.29 |
| removed+said+flinked | 62% | 0.545 | 0.555 | 0.29 | 0.79, 0.29 |

| prediction | predicted | observed | |
|---|---|---|---|
| flinked, corpus FPs per review | 0.48–0.55 | 0.52 | HIT |
| flinked, corpus mean recall | 0.44–0.47 | 0.46 | HIT |
| flinked, bridge | 0.18–0.21; 0.79, 0.29 | 0.18; 0.79, 0.29 | HIT |
| composed, corpus FPs per review | 0.50–0.58 | 0.55 | HIT |
| composed, corpus mean recall | 0.55–0.58 | 0.55 | HIT |
| composed, bridge FPs per review | 0.29–0.33 | 0.29 | HIT |
| composed passes both borderline conditions | — | bridge passes (+0.04), corpus recall fails (+0.09) | MISSED |

- **flinked passes on both data sets.** On the corpus it keeps the two
  intended demotions (claims resting on `chan_count`) and drops the two
  acronym accidents; on the bridge it equals linked.
- **The composed arm fails by one point:** corpus recall +0.091 against
  +0.10. Linkage cost it one valid item, 0afd91 #e2, whose claim names
  `OP_WRITE` and `pNumMsgs` from another file's removed comment: the
  leak, demoted for the reason linkage exists. Its bridge cost, +0.04,
  is inside the limit: linkage takes out two of the bridge deletion
  claims, and the rest is removal objections.

## Sixteenth Measurement — Fresh Corpus Sample

**Status: registered 2026-10-23 before any sample was taken (`1be7179`), scored the same night (Results, below).**

**Why.** The 61 replayed samples have chosen variants three times
(thirteenth, fifteenth, its amendment), and the labels' author knew the
candidates. For a judge-only change, replaying fresh samples is the
live measurement: the judge is deterministic and the model never sees
it; only the replies are stochastic. So one fresh collection decides
every judge candidate, at one collection's GPU cost.

**Design:**
- 35 round-1 samples, 5 per corpus fixture, through `python -m
  eval_harness.corpus run --fixture all --runs 5`: prompt v11.1, judge
  j7, the same indexes, so the requests and fingerprints equal the
  fourteenth's. Retried first attempts are excluded, as before.
- **Labels first.** Every item is labelled in
  `eval_harness/corpus_labels.json` from `corpus score --labels none`
  (which shows j7's split, the current judge's) before any variant is
  replayed on the new records. The labeller knows the candidates; the
  labels are fixed before their results are seen.
- Then `replay --corpus` over the new records only.

**Candidates and rules:**
- **Precision: flinked** (with linked and gapped+flinked reported). It
  becomes the judge change to ship (JUDGE_VERSION j8) if, on the fresh
  samples, FPs per review fall below j7's on the same samples and mean
  recall drops by at most 0.1. Shipping then needs the wiring checks:
  unit tests, fake-driven request checks, the golden suite.
- **Exception: removed+said and removed+said+flinked.** On the fresh
  samples, the corpus conditions: mean recall rises by at least 0.10 and
  FPs per review by at most 0.05. Meeting them does not ship anything;
  it makes backlog #21 (bridge samples with a proposal in the diff's real
  direction, a new bridge baseline, predicted first) the next step, so
  the bridge condition can be judged without the proposal artifact.
- Voting is reported and not a candidate (fifteenth measurement).

**Predictions:**

| metric (fresh samples) | prediction |
|---|---|
| j7 valid share | 50–68% |
| j7 FPs per review | 0.40–0.70 |
| j7 mean recall per known bug | 0.35–0.55 |
| j7 FPs per clean review | 0.20–0.80 |
| j7 evidence demotions per run | 0.30–0.70 |
| first attempts that run away | 0–4 of 35 |
| flinked FPs per review, below j7 by | 0.00–0.10 (passes) |
| flinked mean recall, within | 0.03 of j7 |
| removed+said, recall gain / FP rise | +0.05–0.15 / +0.00–0.06 |
| removed+said+flinked, recall gain / FP rise | +0.04–0.13 / −0.03–+0.04 |

**Expected:** flinked passes and becomes j8, by a small margin, because
linkage acts on few blockers. The exception arms are a coin flip on the
+0.10 recall bar; the recall gain depends on how often the fresh
replies quote removed lines of removed safety checks.

### Results (scored 2026-10-23)

35 samples in 49 minutes, records
`coach_artifacts/measurement_round1_20261024_033005_294ce8.json` to
`..._041842_1711a2.json` (UTC). Two first attempts ran away and were
retried (`40a1ea` on `poll_override_90020bd`, `5cc5be` on
`ecu_support_7d297b4`), leaving 33 scored runs. The labels were
committed in `4d832ea` before the replay ran; j7 reproduced every stored
split.

| variant | valid | FPs per review | mean recall | FPs per clean review |
|---|---|---|---|---|
| j7 | 65% | 0.39 | 0.36 | 0.33 |
| linked, flinked, gapped+flinked | 71% | 0.30 | 0.36 | 0.33 |
| removed+said | 65% | 0.52 | 0.42 | 0.33 |
| removed+said+flinked | 70% | 0.39 | 0.42 | 0.33 |
| vote 2-of-3 @j7 | 79% | 0.53 | 0.39 | 0.00 |

| prediction | predicted | observed | |
|---|---|---|---|
| j7 valid share | 50–68% | 65% | HIT |
| j7 FPs per review | 0.40–0.70 | 0.39 | MISSED LOW |
| j7 mean recall | 0.35–0.55 | 0.36 | HIT |
| j7 FPs per clean review | 0.20–0.80 | 0.33 | HIT |
| j7 evidence demotions per run | 0.30–0.70 | 0.70 | HIT |
| first attempts that run away | 0–4 of 35 | 2 | HIT |
| flinked FPs below j7 by | 0.00–0.10 | 0.09 | HIT |
| flinked mean recall within 0.03 of j7 | — | +0.00 | HIT |
| removed+said recall gain / FP rise | +0.05–0.15 / +0.00–0.06 | +0.05 / +0.12 | HIT / MISSED HIGH |
| removed+said+flinked recall gain / FP rise | +0.04–0.13 / −0.03–+0.04 | +0.05 / +0.00 | HIT / HIT |
| flinked passes, by a small margin | — | passes | HIT |

**By the rules:**
- **flinked passes:** FPs per review 0.39 → 0.30 on the fresh samples,
  mean recall unchanged. It demoted 3 items, all invariant-elsewhere
  false positives whose claims rest on `chan_count`, which the quoted
  hunk never touches, and no valid item. No acronym decided anything
  here, so flinked and linked agree on this sample. By the registered
  rule it becomes judge j8.
- **Neither exception arm earns #21.** Both raise recall by 0.055,
  against the 0.10 bar. removed+said also raises FPs by 0.12: of its 12
  readmitted items, 8 are valid and 4 false, 3 of them deletion claims
  that say "removed" (`notifyDropped()` is removed but still called).
  The removal-word gate does not keep the deletion class out of fresh
  corpus data, so the bridge result was not only the #21 artifact.
- **Voting** stays out (fifteenth). On this sample its clean-fixture
  rate is 0.00, but its FPs per review still rise, 0.39 → 0.53.

**Reading:**
- **The fresh sample agrees with the replayed one on every decision.**
  Linkage helps a little and costs nothing; the removed-line exception
  trades false positives for recall at a bad rate on either data set.
- **The removal-caused loss stays open.** Demoted valid items are as
  common on the fresh sample (17) as on the baseline (17). A judge rule
  cannot tell a removal the change intends from one that breaks
  something; the remaining levers are the prompt or the protocol, and
  they need live measurement.
- **The baseline numbers moved between samples:** valid share 57% →
  65%, FPs per review 0.55 → 0.39, recall 0.46 → 0.36. Same requests,
  same judge. Ranges of this width between two 33-run samples are the
  noise floor any later single-sample comparison on this corpus has to
  clear.

## Claim–Quote Linkage j8 (2026-10-23)

Shipped by the sixteenth measurement's rule: `JUDGE_VERSION`
`j8-claim-quote-linkage`. In `demote_unverified_blockers`, a reviewer
blocker whose quote is verified is still demoted to a question when its
claim names code identifiers and none of them occurs in the hunk its
quote comes from: any line of that hunk, removed lines and the hunk
header included. A token of capital letters only (`PID`, `UI`) is not an
identifier unless the reviewed repo's index defines it as a type or
constant. A claim naming no identifier passes, and so does a quote from
a supplied context, which has no hunks.

- **What it is for:** a verified quote proves the code exists, not that
  it supports the claim. Linkage catches the claim that rests on code
  the quote does not show, as the invariant-elsewhere class does.
- **Measured:** corpus FPs per review 0.39 → 0.30 on fresh samples and
  0.55 → 0.52 on the baseline, recall unchanged on both; bridge 0.25 →
  0.18, race and gate unchanged (thirteenth, fifteenth and sixteenth
  measurements).
- **What changes in code:** `IDENT` and `code_like` moved from
  retrieval to `diff_reader` (retrieval re-exports them);
  `adjudication.hunk_identifiers`, `claim_identifiers` and
  `quote_location` are the judge's, and the replay imports them, so the
  replayed variant and the shipped judge cannot drift. `blocker_evidence`
  gains `assertion`, the claim field alone, which linkage reads; the
  hedge check still reads `claim`. The debate carries the diff's hunk
  identifiers and the index's names in `_Setup`.
- **Records:** linkage demotions are counted with the quote demotions in
  `evidence_demotions` and sit with them at the end of `questions` (`#e`
  in the scorers). The replay reproduces j8 records with `flinked` and
  older ones with j7.
- **Verified:** tests pin linkage's cases (outside the hunk, a removed
  line, the hunk header, acronyms with and without the index, a context
  quote, no hunks) and a debate's j8 stamp; a test checks that the judge
  decides every raw item of the 66 archived corpus runs exactly as the
  replayed `flinked` did. Removing the linkage call, or the debate's
  hunks, fails them. The live golden suite passed 10/10 under j8. Round-1
  requests are unchanged; a debate's round 2
  differs only when linkage moved a blocker.

## Seventeenth Measurement — Repair Pass for Quote Failures

**Status (2026-10-24): drafted before any code or model call, signed off
with the amendment below, implemented, run and scored: not shipped
(Results, below).**

**Why.** The quote rule is the largest recall loss left. Under j8, the 66
archived corpus runs hold 31 valid blockers demoted for their quote: 18
quote code as it read before the change, and 13 quote text found on
neither side. No matching rule can recover the 13; only the model can,
by quoting again. A stronger prompt is not the lever: since v9 the
reviewer prompt has asked for the post-change line a removal leaves
unprotected, and the corpus reviewer quoted removed lines anyway. One
re-quote is on record: in the twelfth measurement, 8dc61a's round 2
restated a demoted race blocker with a quote that passed.

**A correction.** The review that proposed this design said a re-quoted
deletion claim cannot pass linkage, because removed-only names are in
no hunk. That is wrong for j8 as shipped: `hunk_identifiers` takes every
line of a hunk, removed lines and the header included. A deletion claim
naming a removed symbol can pass linkage by quoting a post-change line
of the hunk that removed it. **Containment is empirical:** the false
positive ceilings below are the defense, not linkage.

### Design

**The protocol.** After a round's evidence check (with linkage) and hedge
check, if any reviewer blocker was demoted because its quote was not
found, the reviewer gets one repair call:
- **Request:** the reviewer's system prompt, and as the user message the
  round's transcript followed by a REPAIR section. Each item lists an id,
  the claim, the file, the quote it gave and why it failed: "found only
  in the code before the change" or "not found in that file". The
  section gives no code beyond the transcript and no hint of a line.
- **Reply schema:** `{"repairs": [{"id": 1, "file": "...", "quote": "..."}]}`.
  The claim is never sent back, so it cannot change. The instruction
  makes dropping the default: an item left out stays a question, and so
  does a quote that is not copied exactly from the code after the
  change.
- **Re-entry:** each repair is rebuilt as the original claim with the new
  file and quote, then judged as any blocker is: evidence and linkage
  (j8, on the original claim), then hedging. A passing item moves from
  the end of the questions back to the blockers; a failing one stays.
  Unknown or repeated ids and extra fields are ignored.
- **Settings:** temperature TEMPERATURE_RETRY (0.05), a narrow task;
  `call_agent` with a validator, so a malformed reply is retried and then
  fails closed, leaving every item a question. The request is estimated
  as the input check estimates round 1; over the limit, the repair is
  skipped and the record says so. The bridge fixture's round-1 request
  is estimated at 11,098 of 12,288 tokens, which leaves about 3,500
  characters for the section.

**What is not offered, and why:**
- **Hedge demotions.** A repair turn on a hedged claim invites a
  confident restatement: an exemption from the hedge check by another
  door (#12 closed: a hedged blocker is never a blocker).
- **Linkage demotions.** Their quotes were found; linkage judged that the
  claim rests on code the quote does not show. A repair would let the
  claim fetch that code, which is how the invariant-elsewhere class
  passes. None of the 7 archived linkage demotions is valid.
- **The original reply.** The schema needs only the code and the items,
  which the records and the committed fixtures determine, so every
  request is exactly reconstructible. Whether the reply's presence
  would change repair quality is not tested here.

**Records:** `telemetry.repairs[]`, one entry per repair call, with the
attempt telemetry and, per offered item, its id, failure reason, the
returned quote and the result after re-judging. The split before repair
is kept beside the split after it. Separately, records start storing the
reviewer's raw reply text, whichever arm runs.

**Versions:** a new model-facing template, so PROMPT_VERSION
`v12-repair-pass`. The repair template joins the fingerprint, so every
debate's fingerprint changes; round-1 requests stay byte-identical
(pinned by a test). The repair changes which blockers stand but not the
judge's rules, so JUDGE_VERSION stays j8; the record stamps the repair
pass in its metadata.

### Measurement

**Paired, on archived samples.** Every record's round 1 is already in
hand, so one repair call per record with quote failures gives both arms
on the same replies: A, the j8 split as stored; B, the split after
repair. Pairing removes the between-sample noise the sixteenth measured
(57% → 65% valid on identical requests).
- **Corpus:** the 66 runs of the fourteenth and sixteenth measurements.
- **Bridge:** the 28 labelled samples (G3, the eleventh's and twelfth's
  round 1).
- **Requests:** built with today's templates from each committed fixture
  and the record's proposal: what the shipped repair would send. The G3
  items came from v9's unfenced transcript; their repair calls see
  v11.1's fenced one. The code is the same.
- **Scoring is mechanical.** A repaired item keeps its claim, so its
  label transfers and no new labelling is needed.
- **Development data.** These labels' authors knew the candidates, and
  the samples have chosen judge variants before. The repair variant was
  not selected on outcomes from them, the fresh model calls are the
  measurement, and immutable claims make the labels transfer
  mechanically, which keeps that harmless.

**Baselines (j8, the same records):**
- **Corpus:** 64% valid, 0.41 FPs per review, mean recall 0.41, 0.39 FPs
  per clean review. If every quote failure came back: 0.55 FPs, recall
  0.58. Quote failures: 31 valid, 9 false (6 quote pre-change code).
- **Bridge:** 0.18 FPs per review, race 0.79, gate 0.29. Quote failures:
  4 valid (race claims whose quotes matched nowhere), 12 false (8 quote
  pre-change code), 3 deleted-test objections.

**Rule:** v12 ships if all three hold:
1. corpus mean recall rises by at least 0.10;
2. corpus FPs per review rise by at most 0.05;
3. bridge FPs per review rise by at most 0.05, with race and gate found
   dropping by at most 0.1.

A repair can only readmit, so race and gate can only hold or rise, and
that clause is kept for form. The teeth are the two FP ceilings. The
arithmetic: condition 1 needs about 60% of the possible recall gain;
condition 2 allows about 3 of the corpus's 9 false quote failures back;
condition 3 allows 1 of the bridge's 12. Reported apart: readmitted
bridge deletion claims by count, readmitted deleted-test objections,
repair calls, runaways, size skips and failed repairs.

**Predictions:**

| metric | prediction |
|---|---|
| repair calls, corpus / bridge | 20–30 / 8–15 |
| corpus valid items readmitted | 16–26 of 31 (9–15 of the 18 pre-change quotes, 7–11 of the 13 found nowhere) |
| corpus false items readmitted | 2–5 of 9 |
| corpus mean recall | +0.08 to +0.14 |
| corpus FPs per review | +0.03 to +0.08 |
| bridge false items readmitted | 2–6 of 12 (+0.07 to +0.21 FPs per review) |
| bridge race found | 0.79 → 0.82–0.89 |
| repair-call runaways / size skips | 0–3 / 0–2 |

**Expected by the rule:** v12 fails on the bridge ceiling, through
deletion claims re-quoted from their own hunks; the corpus conditions
are a coin flip. If it fails only there, the next candidate is a
linkage scope that counts post-change lines only for repaired quotes, a
judge change to register on its own, not tuned here.

**Order once signed off:** implement with fake-driven tests (a hedged
item is never offered; a claim cannot change; unknown ids are ignored;
the reply re-enters every check; round-1 requests byte-identical; the
size skip), then the paired repair calls, then the golden suite, then
the results and a commit message.

### Sign-off and amendment (2026-10-24, before any model call)

The three open choices are confirmed as drafted:
1. **Linkage demotions are not offered.** The reason is the mechanism,
   not the 0 of 7 on record: a linkage repair lets a claim shop for the
   code it rests on, which is how the invariant-elsewhere class passes.
   It stands even if a later sample shows a valid linkage demotion.
2. **Each item shows the model its own quote.** It is the model's text,
   not code the judge supplies, and the failure reason means little
   without it. Residual risk: a fabricated quote of the "not found"
   group is echoed back and may be reinforced; the drop-as-default
   instruction is the guard.
3. **Repair calls run at 0.05.** The measurement is of the protocol as
   shipped, so the retry temperature is what should be measured.

**Amendment: the repair pass runs in round 1 only.** The draft said
"after a round's evidence check", which would ship repairs in rounds 2
and later that no measurement sees: every measurement since the fifth
scores round 1. Rounds 2 and later keep v11.1's CRITIQUES section, which
already carries the demoted items as reviewer questions and has
recovered one (8dc61a). This follows the rule that nothing unmeasured
ships, as the v10.1 fence-only amendment did. A repair pass in later
rounds would be its own measurement.

**No golden fixture is added for the repair path.** Live, the golden
fixtures rarely demote a quote, so the suite's repair path is nearly
idle; the fake-driven tests cover its mechanics, and the paired calls
exercise the reply schema live and at scale. Adding a fixture would
also change the suite's count.

**As implemented** (`debate.py`, `adjudication.py`, `agent_client.py`):
- `REPAIR_TEMPLATE`, `REPAIR_ITEM_TEMPLATE` and `REPAIR_REASONS` are
  model-facing, named `v12-repair-pass` (`debate.REPAIR_VERSION`), and
  join the fingerprint only when the pass runs. As measured, debates do
  not run it (Results).
- `demote_unverified_blockers` reports each demotion's reason (`quote`
  or `link`); `repair_offer` keeps the quote failures that have
  evidence, and says whether the quote is found in the code before the
  change (`adjudication.before_sources`); `apply_repairs` re-judges with
  `judge_repaired` (evidence, linkage on the original claim, hedging).
- A round-1 entry gains `repair` (offered, restored, skipped, per-item
  results, and the split before repair) and `telemetry.reviewer_repair`;
  `evidence_demotions` counts what stays demoted, so the scorers' tail
  reading holds. Every accepted reply's text is kept in its telemetry
  entry as `reply`.
- Tests: 188 → 195 at sign-off, 198 after the results (the pass off by
  default, v11.1's fingerprint pinned). Offering linkage demotions,
  repairing in every round, and not decrementing the demotion count
  each fail them.

### Results (scored 2026-10-24)

`python -m eval_harness.repair run|score --set corpus|bridge`; 33 repair
records in `coach_artifacts/measurement_repair_*.json` (22 corpus, 11
bridge), one per source record with quote failures. A dry run before any
call matched the registration: 40 corpus items (31 valid, 9 false) and
19 bridge items; every request was under the size limit.

| arm | corpus valid | corpus FP/rev | corpus recall | bridge FP/rev | bridge race, gate |
|---|---|---|---|---|---|
| A (j8) | 64.0% | 0.409 | 0.413 | 0.179 | 0.786, 0.286 |
| B (after repair) | 64.9% | 0.409 | 0.422 | 0.179 | 0.786, 0.286 |

**Offered items by label class, quote group and result** (`before`:
the quote is found only in the code before the change; `nowhere`):

| set | class | group | offered | restored | re-quoted, demoted again | not returned | call failed |
|---|---|---|---|---|---|---|---|
| corpus | valid | before | 18 | 1 | 0 | 16 | 1 |
| corpus | valid | nowhere | 13 | 1 | 0 | 7 | 5 |
| corpus | false | before | 6 | 0 | 0 | 5 | 1 |
| corpus | false | nowhere | 3 | 0 | 0 | 1 | 2 |
| bridge | valid | nowhere | 4 | 1 | 0 | 2 | 1 |
| bridge | false | before | 8 | 0 | 0 | 7 | 1 |
| bridge | false | nowhere | 4 | 0 | 1 (hedge) | 2 | 1 |
| bridge | deleted test | both | 3 | 0 | 0 | 3 | 0 |

The three restored items: b90266 #e1 and #e2 (the session-lifetime bug,
one from each group) and 5ef90b #e1 (the race, in a run that already
stored it). 61e3c6 #e1, a false lifetime claim, came back with a passing
quote and was demoted by the hedge check.

| prediction | predicted | observed | |
|---|---|---|---|
| repair calls, corpus / bridge | 20–30 / 8–15 | 22 / 11 | HIT / HIT |
| corpus valid readmitted | 16–26 of 31 | 2 | MISSED LOW |
| of the 18 pre-change quotes / 13 found nowhere | 9–15 / 7–11 | 1 / 1 | MISSED LOW |
| corpus false readmitted | 2–5 of 9 | 0 | MISSED LOW |
| corpus mean recall | +0.08 to +0.14 | +0.009 | MISSED LOW |
| corpus FPs per review | +0.03 to +0.08 | +0.000 | MISSED LOW |
| bridge false readmitted | 2–6 of 12 | 0 | MISSED LOW |
| bridge race found | 0.82–0.89 | 0.79 | MISSED LOW |
| repair-call runaways / size skips | 0–3 / 0–2 | 34 of 77 attempts / 0 | MISSED HIGH / HIT |
| fails on the bridge ceiling | — | fails condition 1 instead | MISSED |

**By the rule: v12 fails condition 1** (corpus recall +0.009 against
+0.10) and does not ship. Debates run with `debate.REPAIR_PASS` off and
stay PROMPT_VERSION v11.1 with v11.1's fingerprint (`8e76794ac4946aab`
on the bridge fixture, now pinned by a test); the repair code stays for
the measurement and a successor. The live golden suite passed 10/10 on
the final code.

**Why it failed: the calls mostly did not attempt the task.**
- **First attempts, 33:** 19 ran to the 12,288-token output cap with
  30,000–73,000 characters of thinking, 6 replied in the reviewer's own
  schema (blockers, questions, nits: a fresh review), and 8 replied in
  the repair schema, 2 of them with repairs.
- **Retries:** 18 of the 26 accepted replies came after a corrective
  retry; 16 were an empty list, 14 of those with no thinking (an eval
  count of about 8 tokens). That is the low-thinking retry mode taking
  the default the instruction offered.
- **The request contradicted itself.** The system prompt is the
  reviewer's role specification, and the transcript ends with "RESPOND
  WITH JSON ONLY using your role specification" before the REPAIR
  section asks for another object. The model read it as a request for a
  full review, which is what its runaways and schema violations look
  like. The fake-driven tests answer what they are told, so they could
  not see the conflict; a live pilot of a few calls would have.
- **The registered question is unanswered.** Whether the model can
  re-quote when it attempts the task: 2 of the 8 first attempts in the
  repair schema returned repairs, too few to tell.
- **The guard held:** no false item came back as a blocker on either
  data set. With so few attempts, that says little about the risk.

**What this leaves:** a successor would give the repair call its own
short system prompt (the quoting rules, not the review task) and only
the code part of the transcript, and would pilot a handful of live calls
before the full paired batch. That is a new prompt and a new
registration; the paired archive and the runner are ready for it.

## Eighteenth Measurement — Repair Successor: Ceiling Check and Pilot

**Status (2026-10-24): closed.** The pilot set and the ceiling check
were registered before the check ran and before any successor prompt
was written. The pilot (v13) exited as wiring and its re-pilot (v13.1),
the pilot of record, as incapacity: the model declined its recoverable
valid items. The repair route is closed and the batch did not run (Re-pilot
results, below).

The seventeenth left the registered question unanswered: its calls
mostly did not attempt the task. A successor would give the repair call
its own short system prompt (the quoting rules and its own output keys),
send the diff and layer note without the repo context pack, and carry
its own version name. Before writing that prompt, two steps that cost
no model call or few:

1. **Step 0, the ceiling check (no model).** Whether quotable
   post-change evidence exists for the offered claims at all. If the
   judge would accept no new quote for a claim, no prompt recovers it.
2. **A pilot of 5 live calls** on a fixed set of archived records, with
   a go/no-go bar derived from the ship rule, written here before the
   calls. Drafted after Step 0, since the bar is stated per quotable
   item.

### The pilot set (fixed now, before Step 0; not changed by its result)

| record | fixture | offered items (class/quote group) |
|---|---|---|
| `020932_b90266` | connect_start | #e1 valid/before, #e2 valid/nowhere |
| `035440_2e95fa` | connect_start | #e1, #e2 false/nowhere; #e3, #e4 valid/nowhere |
| `015846_a0d8f9` | trusted_count | #e1 valid/before, #e2 valid/nowhere |
| `035703_61d927` | decode_length | #e1, #e2 false/before; #e3 valid/before |
| `012856_819df9` | bridge | #e1 false/before, #e2 false/nowhere, #e3 false/before |

14 items: 7 valid (3 before, 4 nowhere) and 7 false (4 before, 3
nowhere). Chosen for coverage of the class × quote-group cells, from the
seventeenth's offers only: b90266 is the earliest connect_start record
with valid items in both groups; 2e95fa the only one with false and
valid items found nowhere; a0d8f9 the earliest trusted_count record with
valid items in both groups; 61d927 the only decode_length record with a
valid item; 819df9 the only bridge record with false items in both
groups. Known bias: v12 restored both of b90266's items, so they are
known to be quotable. These 5 records are excluded from the successor's
scored batch.

### Step 0, the ceiling check

`python -m eval_harness.repair ceiling --set corpus|bridge`, over every
item the seventeenth offered (40 corpus, 19 bridge), using the judge's
own functions (`adjudication.evidence_sources`, `hunk_identifiers`,
`judge_repaired`), as replay does:
- **Candidates:** every post-change line of every file in the diff
  (context and added lines, as the evidence check reads them), each as a
  single-line quote naming its file. Multi-line quotes are not tried;
  single lines are a lower bound on the judge's ceiling, close to exact
  since linkage reads whole hunks.
- **Judge-quotable:** some candidate passes `judge_repaired` with the
  item's original claim: the evidence check, linkage on the claim
  (`assertion`), and the hedge check on the claim. Linkage reads the
  quote's hunk, not its line, so any line of a hunk that names one of
  the claim's identifiers passes; this is the judge's ceiling, the one
  the ship rule counts.
- **On-point:** a passing candidate line itself contains one of the
  claim's identifiers (`claim_identifiers` with the index's symbols).
  Claims that name no identifier pass linkage anywhere and are counted
  separately.
- **Hedged:** claims the hedge check demotes whatever their quote;
  never quotable.
- **Ceiling arms:** the corpus recall and FPs per review, and bridge FPs
  per review, if every judge-quotable item is restored, and if only the
  on-point ones are. Against the seventeenth's arm A (j8): corpus recall
  0.413, FPs per review 0.409; bridge 0.179.

**Predictions** (2026-10-24, before the check runs):

| quantity | predicted |
|---|---|
| hedged claims among the offered, corpus / bridge | 2–6 of 40 / 1–4 of 19 |
| judge-quotable, corpus valid / false | 26–31 of 31 / 6–9 of 9 |
| on-point, corpus valid / false | 18–27 of 31 / 4–8 of 9 |
| judge-quotable, bridge valid / false | 3–4 of 4 / 8–12 of 12 |
| judge ceiling, corpus recall / FPs per review | +0.12 to +0.16 / +0.08 to +0.14 |
| on-point ceiling, corpus recall | +0.08 to +0.14 |

**What the result decides:**
- If the judge ceiling's corpus recall gain is below +0.10, no repair
  prompt can pass the seventeenth's ship rule, and the successor is not
  registered.
- If it is +0.10 or more, the pilot is drafted with its restoration
  numbers stated per quotable item ("restored of quotable"), not per
  offered item.
- If the judge ceiling passes but the on-point ceiling does not, a
  passing successor would rest on quotes that do not name what the
  claim names. That is a weakness of hunk-level linkage, and it is
  reported before any pilot.
- The judge ceiling's FP gain against the +0.05 limit says how
  selective the model has to be.

### Step 0 results (2026-10-24)

`python -m eval_harness.repair ceiling --set corpus|bridge`; no model
call, about a second. Pinned by a test (it fails with the hedge check
switched off). The arm labelled "named" in the output is the registered
on-point arm: a passing line names one of the claim's identifiers.
"On-point" in the output also counts claims that name no identifier.

| set | class | group | offered | hedged | judge-quotable | named | names no identifier |
|---|---|---|---|---|---|---|---|
| corpus | valid | before | 18 | 3 | 14 | 5 | 5 |
| corpus | valid | nowhere | 13 | 3 | 10 | 4 | 5 |
| corpus | false | before | 6 | 0 | 6 | 2 | 0 |
| corpus | false | nowhere | 3 | 0 | 3 | 3 | 0 |
| bridge | valid | nowhere | 4 | 0 | 4 | 3 | 0 |
| bridge | false | before | 8 | 1 | 7 | 3 | 3 |
| bridge | false | nowhere | 4 | 1 | 3 | 3 | 0 |
| bridge | deleted test | both | 3 | 0 | 3 | 0 | 1 |

| arm (every such item restored) | corpus recall | corpus FPs per review | bridge FPs per review |
|---|---|---|---|
| A (j8, as archived) | 0.413 | 0.409 | 0.179 |
| judge-quotable | 0.551 (+0.137) | 0.545 (+0.136) | 0.536 (+0.357) |
| named, plus claims naming no identifier | 0.523 (+0.110) | 0.485 (+0.076) | 0.500 (+0.321) |
| named | 0.496 (+0.083) | 0.485 (+0.076) | 0.393 (+0.214) |

| prediction | predicted | observed | |
|---|---|---|---|
| hedged, corpus / bridge | 2–6 / 1–4 | 6 / 2 | HIT / HIT |
| judge-quotable, corpus valid / false | 26–31 / 6–9 | 24 / 9 | MISSED LOW / HIT |
| on-point (named), corpus valid / false | 18–27 / 4–8 | 9 / 5 | MISSED LOW / HIT |
| judge-quotable, bridge valid / false | 3–4 / 8–12 | 4 / 10 | HIT / HIT |
| judge ceiling, corpus recall / FPs | +0.12–0.16 / +0.08–0.14 | +0.137 / +0.136 | HIT / HIT |
| on-point (named) ceiling, corpus recall | +0.08–0.14 | +0.083 | HIT |

**What it shows:**
- **The recall is there, by the judge's count.** The judge ceiling
  clears +0.10, so by the registered rule the successor is not ruled
  out and the pilot is drafted.
- **Of the 7 valid corpus items no quote restores, 6 are hedged.** The
  claim itself hedges, so the judge keeps it a question whatever the
  quote. The seventh (68d66c #e3) names identifiers that no hunk holds.
- **The judge gives no protection against false items here.** All 9
  false corpus items and 10 of 12 false bridge items are
  judge-quotable. Linkage reads the quote's hunk, so any line of a
  linked hunk passes, and a claim naming no identifier passes with any
  line of 8 characters or more. On the false items that stay out, the
  guard is the model's choice alone.
- **Passing would rest partly on loose quotes.** With named quotes only,
  the ceiling is +0.083, below the bar. A successor that passes needs
  some restorations that come from claims naming no identifier (10 of
  the 31 valid corpus items, none of the 9 false) or from lines that
  name nothing the claim names. Hunk-level linkage allows both.
- **The selectivity the ship rule demands:**
  - On the corpus, +0.10 is 73% of the judge ceiling's recall gain.
  - The FP limit of +0.05 allows at most 3 of the 9 quotable false
    items there.
  - On the bridge, it allows at most 1 of the 10 quotable false items
    (1 of 28 reviews is +0.036; 2 is +0.071).
  - The model would have to restore most of its valid claims and
    decline nearly every false one that the judge would accept. Those
    are the claims it made in the first place; the faults are
    correlated.
- **The pilot set:** 6 of its 7 valid items are judge-quotable (a0d8f9
  #e1 is hedged), and all 7 false items are.

**Proposed pilot bar (awaiting sign-off), first attempts only:**
- at least 4 of 5 in the repair schema;
- at most 1 runaway;
- at least 5 of the 6 quotable valid items restored;
- at most 1 of the 4 false corpus items restored;
- none of the 3 false bridge items restored.

Replies that come from retries are counted and reported apart.

### Sign-off of the pilot (2026-10-24, before any model call)

**Two notes on the Step 0 results:**
- **Hedging bounds every fixed-claim protocol.** 6 of the 7 valid corpus
  items that no quote restores fail because the claim itself hedges.
  That is #12's rule ("Hedge Check j6": a hedged claim is never a
  blocker) at work, not a weakness of the model. It is 6 of the 31
  valid items, and about 16% of the recall gain readmitting every quote
  failure would give (with 68d66c #e3). Any protocol that keeps the
  claim fixed, as repair does, loses these. A prompt lever that gets
  the reviewer to state the same bug without hedging is not bound by
  it, since its claim is new.
- **Step 0 is the standard first step for a recall lever.** A ceiling
  check that calls the judge's own functions, registered with its
  predictions, answers in seconds what a GPU batch would answer in
  hours. Each future recall lever runs one before any live call.

**The successor, v13 (`debate.REPAIR_V13_VERSION =
"v13-repair-own-prompt"`)**, used only by `eval_harness.repair run
--variant v13`; debates are unchanged (REPAIR_PASS off, v11.1):
- **System prompt** (`debate.REPAIR_SYSTEM_PROMPT`): checking the quotes
  of findings from the model's own earlier review, without reviewing
  again; the evidence rules of the reviewer prompt's taxonomy (unchanged
  or added lines, copied exactly; removed lines are not evidence; a
  removal-caused defect quotes the code left unprotected; the file is a
  diff path); claims cannot change or be added; leaving a finding out
  costs nothing; its own JSON keys and "An empty list is a valid
  answer". The generic retry message's "the keys from your
  instructions" now names these keys.
- **User message** (`repair_request_v13`): the fenced CODE DIFF section
  (`STATIC_TEMPLATE`, the debate's fence; context "(none provided)"),
  the layer note, and the findings as v12 showed them (claim, file, the
  model's own quote, the reason). No proposal, no repo context pack, no
  transcript closing line.
- **Settings:** the reviewer model at 0.05 (`TEMPERATURE_RETRY`), as in
  v12.
- **Risks seen while writing, kept as designed:** the fence preamble
  calls the diff "the material under review", and the layer notes are
  review rules ("flag any Qt include as a blocker"). Either could pull
  the model back toward reviewing. If the pilot shows re-reviews,
  removing them is the wiring fix for the one re-pilot.

**Exits, first attempts only, in this order** (`repair.pilot_exit`).
"Usable" means a first attempt accepted in the repair schema.
1. **Selectivity, loud:** any false bridge item restored, or 2 or more
   of the 4 false corpus items. The repair line closes.
2. **Wiring:** fewer than 4 usable first attempts, or more than 1
   first-attempt runaway. Fix the prompt and re-pilot once. The
   re-pilot's readings become the pilot of record. False restorations
   from usable first attempts of the first pilot carry over.
   - If the re-pilot also leaves fewer than 4 usable first attempts,
     that is wiring again: the instrument gathered no signal. The pilot
     ends, the batch does not run, and it is recorded as an instrument
     failure, not as a finding about the model. It never trips the
     incapacity exit by default.
3. **Incapacity:** at most 2 of the 6 recoverable valid items restored.
   The repair line closes. The name is given only after reading the
   split:
   - mostly declined (not returned): the model does not re-quote;
   - mostly rejected by the judge: the matcher and the model disagree
     about what a quote is, a separate lever to register later.
4. **Pass:** at least 5 of the 6 recoverable valid items restored, at
   most 1 of the 4 false corpus items, none of the 3 false bridge items.
   The batch runs.
5. **Marginal:** anything else (valid 3–4 of 6, false within the
   tripwires). The batch runs with the prompt unchanged, and the ship
   rule decides.

Valid items from a call whose first attempt was not usable count as not
restored. Replies from retries are reported apart and count toward no
exit. Every nonconforming reply is read, even when the bar passes.

Why loud failures only: with 6 valid and 7 false items, a model exactly
at the ship rule's rates passes every clause about 21% of the time, a
comfortably shippable one (85% valid, 15% / 5% false) about 59%, and a
clearly failing one (50%, 50% / 30%) about 1%. Closing the line on a
marginal miss would let n = 7 make the batch's decision.

**Pilot predictions:**

| quantity | predicted (point) |
|---|---|
| usable first attempts | 3–5 of 5 (4) |
| first-attempt runaways | 0–2 (1; 819df9's 30K-char bridge request most likely) |
| first-attempt re-reviews | 0–1 |
| valid restored, of 6 recoverable | 2–5 (4) |
| false corpus restored, of 4 | 0–2 (1) |
| false bridge restored, of 3 | 0–1 (0) |
| exit | marginal most likely, then selectivity |

**The batch, if it runs:** the seventeenth's sets without the pilot's
records. That is 62 corpus reviews with 29 offered items and 27 bridge
reviews with 16 (`repair ceiling --set corpus|bridge --batch`).

| | corpus recall | corpus FPs per review | bridge FPs per review |
|---|---|---|---|
| A (j8) | 0.437 | 0.435 | 0.185 |
| judge ceiling (every recoverable item restored) | 0.550 (+0.113) | 0.516 (+0.081) | 0.444 (+0.259) |

Recoverable in the batch: 18 of 24 valid corpus items, 5 of 5 false
corpus items, 7 of 9 false bridge items. Of the 6 valid corpus items no
quote restores, 5 are hedged. The ship rule, unchanged, therefore asks for:
- about 88% of the batch's recoverable recall gain (+0.10 of +0.113);
- at most 3 of the 5 recoverable false corpus items (3 of 62 reviews is
  +0.048);
- at most 1 of the 7 recoverable false bridge items (1 of 27 is
  +0.037).

The pilot's exclusion lowered the batch's ceiling from +0.137 to
+0.113, because b90266, 2e95fa, a0d8f9 and 61d927 hold 6 of the 24
recoverable valid items.

**Batch prediction, stated per recoverable item:** valid restored
55–85% of 18, so corpus recall +0.06 to +0.10; false corpus 1–3 of 5;
false bridge 1–3 of 7. Predicted to fail condition 1, which needs
restoration near 88%. Condition 3 (bridge FPs) is the next most likely
failure.

### Pilot results (2026-10-24): exit 2, wiring

`python -m eval_harness.repair run --variant v13 --pilot`, then
`python -m eval_harness.repair pilot`. Records:
`coach_artifacts/measurement_repair_v13_<source>.json` (5; repair
fingerprint `09a782e33e7aa6d6`). About 21 minutes on the GPU.

| call | first attempt | reply from | thinking chars per attempt | repairs |
|---|---|---|---|---|
| a0d8f9 | usable (187 s) | first | 32,795 | 2 |
| b90266 | usable (30 s) | first | 5,851 | 0 |
| 2e95fa | usable (36 s) | first | 7,199 | 1 |
| 61d927 | runaway | retry (32 s) | 53,046; 6,866 | 0 |
| 819df9 (bridge) | runaway | failed, 3 runaways | 47,884; 49,326; 73,627 | — |

**Items by reply source, class, quote group and result:**

| reply from | class | group | restored | rejected by the judge | declined | call failed |
|---|---|---|---|---|---|---|
| first | valid | before | 0 | 1 (hedge; not recoverable) | 1 | 0 |
| first | valid | nowhere | 1 | 0 | 3 | 0 |
| first | false | nowhere | 0 | 1 (quote) | 1 | 0 |
| retry | valid | before | 0 | 0 | 1 | 0 |
| retry | false | before | 0 | 0 | 2 | 0 |
| failed | false | before / nowhere | 0 | 0 | 0 | 2 / 1 |

**Exit 2, wiring:** 3 usable first attempts (fewer than 4) and 2
first-attempt runaways (more than 1). No false item was restored, so
nothing carries over to the re-pilot.

| prediction | predicted | observed | |
|---|---|---|---|
| usable first attempts | 3–5 (4) | 3 | HIT, low edge |
| first-attempt runaways | 0–2 (1; 819df9 most likely) | 2 (819df9, 61d927) | HIT, high edge |
| first-attempt re-reviews | 0–1 | 0 | HIT |
| valid restored, of 6 | 2–5 (4) | 1 | MISSED LOW |
| false corpus restored, of 4 | 0–2 (1) | 0 | HIT |
| false bridge restored, of 3 | 0–1 (0) | 0 (call failed) | HIT, no data |
| exit | marginal, then selectivity | wiring | MISSED |

**Reading the replies:**
- **No re-reviews this time:** every accepted reply is in the repair
  schema, and so is every runaway's visible work.
- **The runaways judge whether each finding is true**, which the
  system prompt asks for ("decide whether the code after the change
  shows it").
  - 61d927's thinking takes the findings one at a time and concludes
    that its false ones are not shown, which is correct.
  - 819df9's three attempts rebuild `onFrame` in full and end weighing
    "genuine thread safety concerns", which echoes the bridge layer
    note's "Thread-safety requirements are ACTIVE".
- **The fast replies decline.**
  - b90266 (30 s) and 2e95fa (36 s) declined 4 recoverable valid items.
    v12 had restored both of b90266's.
  - 2e95fa's one repair, of a false item, quoted 12 lines with comments
    and failed the quote check.
- **The one call in between, a0d8f9 (187 s), re-quoted both items:**
  #e2 was restored, and #e1 failed the hedge check as Step 0 said it
  must.
- **The model appears bimodal:** it either declines quickly or
  deliberates until the cap. Nothing here says which way more thinking
  tips its selectivity.

**Next, under the binding:** one re-pilot with a fixed prompt, whose
readings become the pilot of record. The fix is not chosen yet.

### Re-pilot, v13.1 (registered 2026-10-24, before its calls)

**The fix (option 1):** v13 without the two parts registered as review
context. `debate.REPAIR_V13_1_VERSION = "v13.1-repair-no-review-context"`
(repair fingerprint `71b3eb178777e3af`; v13's stays `09a782e33e7aa6d6`).
- **No layer note.**
- **The fence preamble without "the material under review":**
  `REPAIR_STATIC_TEMPLATE` opens "The CODE DIFF and CODE CONTEXT below
  each sit between a BEGIN DATA line and an END DATA line". The fence,
  its mark and the two DATA sections are v13's.
- **Everything else is v13's:** the system prompt, the findings, the
  closing line, the reviewer model at 0.05 and the 12,288-token output
  cap.

Requests are about 350 characters shorter (6,565 to 30,106 with the
system prompt).
- **Considered and not taken:**
  - **A task-specific output cap.** a0d8f9's productive call used
    9,272 output tokens, thinking included, so a cap of a few thousand
    would have made it a runaway. A cap safe for it saves little, and
    a capped attempt is still a runaway first attempt, so the exit
    would not change.
  - **Option 2,** which recasts the task as a lookup. It would remove
    the model's own discrimination, which is what the pilot measures
    and the only protection repairs have.

**Records:** `coach_artifacts/measurement_repair_v13.1_<source>.json`.
Read with `python -m eval_harness.repair pilot --variant v13.1`. The
re-pilot's readings are the pilot of record. v13's pilot restored no
false item, so nothing carries over.

**Amendment to the exits: an arithmetic exit**, checked after
incapacity and before the bar.
- **The rule:** if the restored share of the recoverable valid items
  in usable first attempts is below 59%, the repair line closes on
  arithmetic, recorded as such. With all 6 read, that is 3 or fewer
  restored.
- **Why 59%:** a rate r projects a batch gain of about r × 0.113, and
  59% is the rate that reaches two-thirds of the +0.10 bar (+0.067).
  3 of 6 projects +0.057; 4 of 6, +0.075.
- **Why it rarely misfires:** passing the batch takes about 88%
  restoration, and a model at 88% restores 3 or fewer of 6 about 3% of
  the time.
- **The denominator** is the items of usable first attempts, so a
  runaway call cannot trigger the arithmetic exit; that stays wiring.
  The pass bar still counts items from unusable calls as not restored.
- **What it changes:** 3 of 6 moves from marginal (the batch runs) to
  closed. 4 of 6 stays marginal.

The other exits stand as registered, and a second wiring failure ends
the pilot as an instrument failure.

**Predictions for the re-pilot:**

| quantity | predicted (point) |
|---|---|
| usable first attempts | 3–5 (4) |
| first-attempt runaways | 0–2 (1; a 61d927-type deliberation) |
| 819df9 (bridge) first attempt usable | 40% |
| valid restored, of 6 recoverable | 1–4 (2) |
| false corpus / bridge restored | 0–1 of 4 / 0–1 of 3 |
| exit | incapacity or arithmetic most likely, then wiring |

If a 61d927-type runaway persists without the review context, it is
recorded as the reviewer's open-ended runaway (#16, #19) appearing in a
narrow task, not as contamination.

### Re-pilot results (2026-10-24): exit 3, incapacity (declined); the repair line closes

`python -m eval_harness.repair run --variant v13.1 --pilot`, then
`python -m eval_harness.repair pilot --variant v13.1`. Records:
`coach_artifacts/measurement_repair_v13.1_<source>.json` (5). About 15
minutes on the GPU. This is the pilot of record.

| call | first attempt | reply from | thinking chars per attempt | repairs |
|---|---|---|---|---|
| a0d8f9 | runaway | retry 2 (166 s) | 48,337; 49,336; 34,696 | 2 |
| b90266 | usable (28 s) | first | 5,900 | 0 |
| 2e95fa | usable (63 s) | first | 14,287 | 0 |
| 61d927 | usable (128 s) | first | 28,132 | 0 |
| 819df9 (bridge) | usable (32 s) | first | 4,495 | 0 |

**Items by reply source, class, quote group and result:**

| reply from | class | group | restored | rejected by the judge | declined |
|---|---|---|---|---|---|
| first | valid | before | 0 | 0 | 2 |
| first | valid | nowhere | 0 | 0 | 3 |
| first | false | before | 0 | 0 | 4 |
| first | false | nowhere | 0 | 0 | 3 |
| retry | valid | before | 0 | 1 (hedge; not recoverable) | 0 |
| retry | valid | nowhere | 1 | 0 | 0 |

**Exit 3, incapacity:** 4 usable first attempts and 1 runaway, so the
wiring exit does not apply. 0 of the 5 recoverable valid items read in
usable first attempts were restored; a0d8f9 #e2 was the sixth, in the
runaway call. No false item was restored. **Named after the split:
declined.** All 5 were left out by the model, and the judge rejected
none, so the matcher-disagreement reading does not arise. **The repair
line closes;** the batch does not run.

| prediction | predicted | observed | |
|---|---|---|---|
| usable first attempts | 3–5 (4) | 4 | HIT |
| first-attempt runaways | 0–2 (1; a 61d927-type) | 1 (a0d8f9, another type) | HIT |
| 819df9 first attempt usable | 40% | yes | — |
| valid restored, of 6 recoverable | 1–4 (2) | 0 | MISSED LOW |
| false corpus / bridge restored | 0–1 / 0–1 | 0 / 0 | HIT / HIT |
| exit | incapacity or arithmetic, then wiring | incapacity | HIT |

**Reading the replies:**
- **Removing the review context removed its runaways.** Under v13,
  819df9 ran away three times into thread safety; under v13.1 it
  declined in 32 s. 61d927 answered in 128 s instead of running away.
  The layer note was contamination.
- **The remaining runaway is new: indecision about removal-caused
  findings.**
  - a0d8f9's thinking drafts the right repairs, then doubts them ("I'm
    not sure if I should include both findings. Let me re-read the
    task"). It reasons that "the code after the change shows the
    removal happened", and goes round again until the cap.
  - The system prompt asks whether the code after the change "shows"
    a finding, and also says to quote the code a removal leaves
    unprotected. For removal-caused defects, which 18 of the 31 valid
    corpus offers are, the model reads those as in tension.
  - This is not the reviewer's open-ended runaway (#16, #19), since it
    loops on one decision rather than searching.
- **The fast declines hold without the review context.** b90266
  declined in 28 s both times, though v12 restored both its items and
  Step 0 shows them recoverable. Across both pilots, usable first
  attempts restored 1 of 10 recoverable valid items read.
- **The one restoration rests on a loose quote.** In both pilots it
  came from a0d8f9 #e2. Under v13.1 its quote was a comment line ("/*
  Frames are collected whatever the status: per J2534-1 a read that"),
  which passes only because linkage reads the whole hunk.
- **The guard held, and says little.** No false item came back in
  either pilot; with the valid ones declined too, that shows a model
  that declines, not one that discriminates.

**Conclusion:** within this measurement, the reviewer model does not
re-quote its own quote-failed claims when asked in a narrow call. It
declines valid and false alike, or deliberates to the cap over whether
a removal can be shown. The repair route (v12, v13, v13.1) is closed. A
recall lever for the removal-caused loss would have to work when the
claim is first written: in round 1's prompt, or as a new claim, which
is also the only route past the 6 hedged items. The pack-side work on
invariant-elsewhere is the other candidate. Neither is registered.
Debates are unchanged: v11.1 with the repair pass off.

## Nineteenth Measurement — Removal-Caused Defects Quoted in Round 1

**Status (2026-10-25): drafted before any code change or model call,
reviewed, and signed off with the amendments below. Implemented as
PROMPT_VERSION `v14-removal-quotes`, piloted, run and scored. It did not
ship: corpus recall rose 0.05 against the 0.10 bar, and bridge race
recall fell 0.23 (Results). Debates stay v11.1.**

**Why.** The quote rule is still the largest recall loss. Under j8, the
66 archived corpus runs hold 31 valid blockers demoted for their quotes,
0.47 per run, and the count held between samples (17 and 17 under j7,
sixteenth measurement). The eighteenth measurement closed the route of
fixing quotes after the fact: asked in a narrow call, the model declined
its own valid claims. A lever has to act when the claim is first
written, in round 1's prompt.

The seventeenth measurement's "Why" said a stronger prompt is not the
lever, because v9's prompt already asks for the post-change line a
removal leaves unprotected. Two things found since then argue against
that.
- **The prompt points two ways.** The schema line asks for "the code
  that shows it", while the rules ask for the post-change line a removal
  leaves unprotected. For a removal, the code that shows it is the
  removed line. Under v13.1 the a0d8f9 runaway went round this exact
  tension until it hit the cap: "the code after the change shows the
  removal happened" (eighteenth, "Reading the replies"). The round-1
  prompt has the same pair of instructions
  (`reviewer_prompt.REVIEWER_SYSTEM`).
- **The quote failures have a shape the prompt can name.** A scratch
  tally of the offered items' quote lines, each matched after
  collapsing whitespace against the fixture's removed and post-change
  lines (this is not the judge's matcher, so treat the split as
  approximate):

  | set | class | quote mixes post-change and removed lines | removed lines only | no removed line |
  |---|---|---|---|---|
  | corpus | valid (31) | 16 | 10 | 5 |
  | corpus | false (9) | 0 | 6 | 3 |
  | bridge | valid (4) | 2 | 0 | 2 |
  | bridge | false (12) | 3 | 6 | 3 |
  | bridge | deleted test (3) | 0 | 3 | 0 |

  Two counts of the same 31 differ by what they count. The judge's
  grouping (seventeenth) puts 18 in "before": the whole quote is found
  in the code before the change. This tally finds 26 quotes with at
  least one removed line: those 18, and 8 of the 13 found nowhere, which
  mix removed lines with lines the matcher places nowhere.

  On the corpus, the valid failures are mostly blocks copied across a
  removal: the kept lines are around the removed check, and the removed
  check is in the middle. The judge drops removed lines from the
  evidence, so the kept lines alone are adjacent there and would pass.
  No false failure has that shape. The false removed-only quotes are
  mostly the deletion class: claims that removed code is still present.
  The new rule gives them no legitimate quote, but they can adapt:
  linkage reads the whole hunk, removed lines included, so a deletion
  claim can pass by quoting an unrelated post-change line of its own
  hunk (Step 0 of the eighteenth found a passing line for all 9). The 6
  are 0.09 false positives per review over 66 runs; half of them moving
  would add 0.045, nearly all of condition 2's 0.05. On the bridge, 3
  false mixed blocks stand against 2 valid, so the bridge ceiling is
  the other risk.

### Design

**Change** (PROMPT_VERSION `v14-removal-quotes`; reviewer system prompt
only, so the header-scoped and implementation prompts both change):

The schema's quote field, from
`"the code that shows it, copied exactly from the CODE DIFF as it reads after the change"`
to
`"the code as it reads after the change, one line or adjacent lines, copied exactly from the CODE DIFF"`
(amended at sign-off; the draft said "one line of the code", which
contradicted the rule's "or lines that are adjacent").

The quote rule, from

```
- Every blocker quotes the code that shows the violation as it reads AFTER the
  change: unchanged or added lines, copied exactly, without the leading '+' or
  space. Removed lines no longer exist and are not evidence; if the problem is
  caused by a removal, quote the code after the change that the removal leaves
  broken or unprotected. Blockers are checked mechanically: a blocker whose
  quote is not found in that file's code after the change is moved to
  questions.
```

to

```
- Every blocker quotes the code AFTER the change: an unchanged or added line,
  copied exactly, without the leading '+' or space. Quote one line, or lines
  that are adjacent after the change. Never include a removed ('-') line, and
  never shorten a quote with '...'.
- A removal can be the violation. Then the claim names what was removed, and
  the quote is the line after the change that now runs without it: the call,
  use or path the removed code checked or protected. A removed line is never
  the quote, even when its removal is the problem. For example, if the diff
  removes "if (handle == NULL) return ERR_INVALID;", quote the line that now
  runs unchecked, such as "handle->close(handle);".
- Blockers are checked mechanically: a blocker whose quote is not found in
  that file's code after the change is moved to questions.
```

The other rules, the CHECK FOR list and the scope clauses are unchanged.

**The example** was chosen so that it matches no known bug: no corpus
fixture's known bug and neither bridge bug (race, gate) is a null check.
An example can still prime null-check claims; the false positives by
class are reported, so that would show up.

**What it does not address:** the 6 valid corpus items the hedge check
demotes (#12 stays closed), and deleted-test objections (since j4 they
can't be blockers).

**Versions:** a reviewer prompt change, so every request changes,
round 1 included, and with it every fingerprint; the tests' fingerprint
pin moves. JUDGE_VERSION stays j8. The golden suite runs live after the
change, since its header fixture uses the changed prompt. The probe and
bake-off read the same prompt text, so their requests change too; their
logs predate v9 already. The prompt grows by about 350 characters (about
120 tokens at the input check's floor), which leaves the bridge fixture's
round-1 request, estimated at 11,098 tokens, under the 12,288 limit.

### Measurement

**Pilot first (the seventeenth's lesson).** Three live round-1 calls
before the batch, one each on `trusted_count_6420f09`,
`connect_start_4a86231` and the bridge fixture. Only their telemetry and
schema validity are read, not their claims, and they are not scored.
Exit to a wording fix if 2 or more of the 3 first attempts run away or
fail schema validation.

**Samples:** fresh round-1 samples at v14, judge j8, the same fixtures,
indexes and proposals as the fourteenth and sixteenth measurements:
- **Corpus:** `python -m eval_harness.corpus run --fixture all --runs 10`
  (70 runs; sign-off).
- **Bridge:** 10 samples with the original proposal (kept for
  comparability; #21 not taken up here) through `eval_harness.round1
  run`.
- Retried first attempts are excluded, as before.

**Labels first:** every item of the new records is labeled
(`corpus_labels.json`; `labels.json` for the bridge) before anything is
scored. The labeler knows the arm, since all samples are v14.

**Baselines (j8, archived, the same requests apart from the prompt):**
- **Corpus, 66 runs:** 64% valid, 0.41 FPs per review, mean recall 0.41
  stored (0.59 counting demoted items), 0.39 FPs per clean review, 0.47
  valid quote failures per run.
- **Bridge, 28 samples:** 0.18 FPs per review, race 0.79, gate 0.29.

**Rule (the seventeenth's bars; race and gate now matter, since a
round-1 prompt change can lose them):** v14 ships if all three hold:
1. corpus mean recall (stored) rises by at least 0.10;
2. corpus FPs per review rise by at most 0.05;
3. bridge FPs per review rise by at most 0.05, with race and gate found
   each dropping by at most 0.1.

A secondary rule for a recall gain of +0.05 to +0.09 was added at
sign-off (below).

**Reported apart:** valid quote failures per run, split by the shape
above (the mechanism); recall counting demoted items (if it moves, the
prompt changed which claims are made, not only how they are quoted);
FPs by class, null-check claims included; deletion-class blockers
stored per run on the bridge; runaways.

**Noise:** between two 33-run samples on identical requests, valid share
moved 57% → 65%, FPs per review 0.55 → 0.39 and recall 0.46 → 0.36
(sixteenth). The recall bar is the same size as that swing, which is why
the sample is twice the usual size.

**Predictions:**

| metric | prediction |
|---|---|
| pilot exit | passes (0–1 of 3 bad first attempts) |
| first-attempt runaways, corpus | 0–6 of 70 (archived: 4 of 70) |
| valid quote failures per run | 0.47 → 0.15–0.30 |
| corpus valid share | 62–74% |
| corpus FPs per review | 0.33–0.50 |
| corpus mean recall, stored | +0.04 to +0.14 |
| corpus recall counting demoted items | within 0.06 of 0.59 |
| corpus FPs per clean review | 0.20–0.60 |
| bridge FPs per review | 0.14–0.32 |
| bridge race / gate | 0.60–0.90 / 0.10–0.50 |

**Expected by the rule:** the mechanism works (quote failures fall by
about half), and condition 1 is a coin flip (point estimate +0.08). If
condition 3 fails, it fails through deletion or removal-objection
blockers now quoted from post-change lines of their own hunks, which
linkage lets through (seventeenth, "A correction").

**Order once signed off:** edit the prompt and bump PROMPT_VERSION, then
move the fingerprint pin and run the unit tests; then the pilot; then
the batch; then the labels; then the score; then the golden suite;
then the results and a commit message.

### Sign-off (2026-10-25, before any model call)

The draft offered three choices; each was decided as recommended, after
a review of the draft:
1. **70 corpus runs** (`--runs 10`), because the recall bar is as large
   as the swing between two 33-run samples. The bridge takes 10.
2. **The example stays.** The a0d8f9 tension was over what a removal's
   quote is, and an example settles that in one line. Priming shows up
   in the false positives by class.
3. **The primary bars stay the seventeenth's,** so the recall levers
   stay comparable across this ADR.

**Amendments from the review:**
- **The schema line** allows adjacent lines, as the rule does (Design).
  A strict one-line rule would discard what the mixed blocks need: their
  kept lines around a removed middle line, which are adjacent in the
  judge's evidence.
- **"Never shorten a quote with '...'"** is stricter than the judge,
  which splits a quote at an ellipsis and checks each part. A stricter
  prompt is safe, so it stays.
- **The 18 and 26 figures** are both named in the "Why", and so is the
  deletion class's way past the new rule, with its 0.09.

**A secondary ship rule, added now so that it is not chosen after the
result.** If condition 1 fails with corpus mean recall up by +0.05 to
+0.09, v14 still ships, as a partial, if all of these hold:
- valid quote failures per run fall from 0.47 to 0.24 or fewer;
- conditions 2 and 3 hold.

The reason: recall per bug moved by 0.10 between identical samples,
while valid quote failures held (17 and 17). A halving of the stable
count shows that the prompt does what it is for, where a recall gain of
that size alone could be noise. The cost of shipping on it is the
baseline: v14's samples become what later round-1 measurements compare
with.

**The pilot's records are kept and excluded by id.** They land in
`coach_artifacts/` beside the batch's and are named in the results, so
the scoring globs leave them out.

**As implemented:** `reviewer_prompt.REVIEWER_SYSTEM` as in Design, and
PROMPT_VERSION `v14-removal-quotes`. The bridge fixture's debate
fingerprint is `0e64900137072695` (v11.1: `8e76794ac4946aab`), pinned by
a test. Its round-1 request is estimated at 11,224 of 12,288 tokens.
Tests: 204, and both version pins fail on the v11.1 prompt.

### Pilot (2026-10-25): passes

Three records, excluded from scoring:
`measurement_round1_20261026_011519_4ce224` (trusted_count),
`..._011610_8daed9` (connect_start) and `..._011932_4513de` (bridge).
All three first attempts were accepted (`done_reason` stop): 1,231,
8,872 and 2,571 output tokens, in 51 s, 201 s and 86 s. None ran away,
so the exit (2 or more bad first attempts) is not met, and the batch
runs unchanged. The runner's progress line also prints each record's
stored-blocker count, which the pilot did not mean to read: 0, 0 and 2.
One sample each says nothing at the baseline's spread (trusted_count
stored 4 blockers in 10 runs), and no decision rests on it.

### Results (scored 2026-10-25): not shipped

80 records, `measurement_round1_20261026_012123_2a7cd9` to
`..._040210_bd89a5` (UTC): 10 bridge samples, then 70 corpus samples.
Two first attempts ran away to the output cap and were retried, so they
are excluded: `71f77e` (bridge) and `fcda47` (`init_noops`). That leaves
9 bridge and 69 corpus runs. Every item was labeled before anything was
scored (`corpus_labels.json`, sample `v14`; `labels.json`, set
`nineteenth`). A test pins the corpus counts (69 runs, 80 stored, 56
valid). Both arms are judged by j8. The stored split reproduces exactly.

| | baseline (j8, archived) | v14 | change | bar |
|---|---|---|---|---|
| corpus mean recall, stored | 0.413 | 0.464 | +0.051 | ≥ +0.10 |
| corpus FPs per review | 0.409 | 0.348 | −0.061 | ≤ +0.05 |
| bridge FPs per review | 0.179 | 0.111 | −0.068 | ≤ +0.05 |
| bridge race found | 0.786 | 0.556 | −0.230 | ≥ −0.1 |
| bridge gate found | 0.286 | 0.556 | +0.270 | ≥ −0.1 |
| corpus valid quote failures per run | 0.470 | 0.304 | −35% | ≤ 0.24 (secondary) |
| corpus valid share | 64% | 70% | | |
| corpus recall counting demoted items | 0.588 | 0.691 | +0.103 | |
| corpus FPs per clean review | 0.389 | 0.211 | | |

**By the rules: v14 does not ship.**
- **Primary rule:** condition 1 fails (recall +0.051), and so does
  condition 3 (race −0.23). Condition 2 holds.
- **Secondary rule:** the recall gain is inside its band by one
  thousandth, but the mechanism clause fails: valid quote failures fell
  to 0.30, not to 0.24. Condition 3 fails here too.

`reviewer_prompt.py` has the v11.1 text again, and the bridge
fingerprint is `8e76794ac4946aab` once more (pinned). Because the
debates' prompt is the one the live golden suite already passed with,
the suite was not rerun.

| prediction | predicted | observed | |
|---|---|---|---|
| pilot exit | passes | passes | HIT |
| first-attempt runaways, corpus | 0–6 of 70 | 1 | HIT |
| valid quote failures per run | 0.15–0.30 | 0.304 | MISSED HIGH |
| corpus valid share | 62–74% | 70% | HIT |
| corpus FPs per review | 0.33–0.50 | 0.348 | HIT |
| corpus mean recall, stored | +0.04 to +0.14 | +0.051 | HIT |
| recall counting demoted items | within 0.06 of 0.59 | 0.691 | MISSED HIGH |
| corpus FPs per clean review | 0.20–0.60 | 0.211 | HIT |
| bridge FPs per review | 0.14–0.32 | 0.111 | MISSED LOW |
| bridge race / gate | 0.60–0.90 / 0.10–0.50 | 0.556 / 0.556 | MISSED LOW / MISSED HIGH |
| quote failures fall by about half | — | by a third | MISSED |
| condition 3 fails through deletion claims | — | fails through the race | MISSED |

**Corpus demotions** (shapes from the same scratch tally as the "Why".
"Mixed" includes a removed block quoted with a closing brace that is
also a context line, so it overstates quotes that span a removal):

| class | mixed | removed only | no removed line | linkage | all |
|---|---|---|---|---|---|
| valid, baseline (66 runs) | 16 | 10 | 5 | 0 | 31 |
| valid, v14 (69 runs) | 9 | 8 | 4 | 5 | 26 |
| false, baseline | 0 | 6 | 3 | 5 | 14 |
| false, v14 | 4 | 0 | 0 | 4 | 8 |

**Reading:**
- **More of the gain came from what was claimed than from how it was
  quoted.** Recall counting demoted items rose by 0.10, against 0.05 for
  stored recall. The new claims are mostly removal-caused bugs: the
  `payloadHex` clamp (`payload_length_unclamped`, stored in 0 of 9
  baseline runs, 3 of 10 here), `unsubscribed_rows_freeze` (0.10 →
  0.30) and `static_batch_replay` (0.20 → 0.40). A few others fell:
  `poll_ignored` 0.11 → 0, `backoff_overshoot` 0.90 → 0.80,
  `decode_length_8` 1.00 → 0.90. A one-run change on one fixture is
  within this corpus's noise.
- **The quote instruction was followed only in part.** 17 of the 21
  valid quote failures still quote removed lines, and several keep the
  `-` marker the prompt forbids (`a4b595`, `4e2591`, `7433de`). Removed
  comments are still the most-quoted text on `trusted_count`.
- **Where it was followed, linkage demoted the result.** Five valid
  claims (the baseline had none) quote a post-change line as v14 asks,
  for example the lambda that now carries the session, or the drop path
  that lost its report. In each case the identifiers the claim names
  appear only in another hunk, such as the removed destructor cleanup,
  so j8 demoted them. Most removal-caused defects take effect away from
  the removal, which is exactly where v14 sends the quote and where
  hunk-level linkage refuses it.
- **On the bridge, attention moved from the race to the gate.** The gate
  is the removed in-flight bound, and a prompt about removals found it
  in 5 of 9 runs, against 8 of 28 before. The race fell from 22 of 28 to
  5 of 9. Nine samples are few, but the rule is the rule.
- **False positives fell, and no example priming showed up.** Corpus
  FPs per review fell from 0.41 to 0.35, and on clean fixtures from 0.39
  to 0.21. There are no null-check claims, and no stored deletion claim.
  The sixteenth measurement showed swings of this size between
  identical samples, so this is not credited to v14.

**Conclusion:** the stronger round-1 quote rule moved recall by half the
bar on the corpus and cost the bridge its race. The removal-caused
loss is not mainly a wording problem. The model keeps quoting removed
text, and when it quotes the code a removal affects instead, linkage
often refuses it, because that code is in another hunk. Linkage scope
for such claims is a judge question (the eighteenth's Step 0 showed
linkage is also what keeps false claims out), and it is not registered.
Debates are unchanged: v11.1, j8.

### Amendment (2026-10-26): cross-hunk linkage, closed by its ceiling

The Results' third reading point suggests a judge variant: linkage that
looks beyond the quote's hunk, for claims about removed code. It was
checked offline, without a live run, and closed.

**Method.** Any cross-hunk linkage sits between j8 and no linkage at
all. No linkage is the replay's existing `j7` variant: the same quote
check, then the hedge check, without linkage. So `j7` is the ceiling,
and `flinked` reproduces j8. Both come from the committed replay, scored
with the committed labels:
- **Corpus, v11.1 (66 runs):** `python -m eval_harness.replay --corpus
  "coach_artifacts/measurement_round1_20261024_0*.json"`, the
  fourteenth and sixteenth samples.
- **Corpus, v14 (69 runs):** the same command over
  `measurement_round1_20261026_01[45]*.json` and
  `measurement_round1_20261026_0[234]*.json`. These are this
  measurement's corpus runs; `--corpus` leaves out the bridge record
  among them.
- **Bridge:** `python -m eval_harness.replay --diff
  docs/fixtures/qttune_bridge_refactor.diff` over this measurement's 10
  bridge records and the 28 archived ones
  (`measurement_round1_20261023_01*`, `measurement_round2_20261023_*`).

The replay prints two decimals; the figures below are the same
functions' unrounded output.

| arm | judge | mean recall | FPs per review |
|---|---|---|---|
| corpus, v11.1 | j8 | 0.413 | 0.409 |
| corpus, v11.1 | no linkage (`j7`) | 0.413 (+0.000) | 0.470 (+0.061) |
| corpus, v14 | j8 | 0.464 | 0.348 |
| corpus, v14 | no linkage (`j7`) | 0.482 (+0.018) | 0.377 (+0.029) |

On the bridge, race found is the same under `j7` and `flinked` in every
set (v14: 0.556 under both).

The two arms differ as they should:
- **v11.1 gains nothing.** Its 66 runs have no valid linkage demotion,
  as the sixteenth found: there, linkage demoted invariant-elsewhere
  claims and no valid ones.
- **v14 gains little.** Of its 5 valid linkage demotions, 2 (`fa3031`
  #e1, `e6c961` #e1) are hedged and would be demoted anyway. One
  (`e530e8` #e1) restates a bug its run already stored. Only 2
  (`5e7ae7` #e1, `90e7f3` #e1) add a bug to their run.

**Closure.** No cross-hunk linkage variant can pass the bar:
- On the shipped prompt it adds false positives and no recall.
- On v14 it reaches +0.069 corpus recall over the v11.1 baseline,
  against +0.10, even with linkage removed entirely.
- The bridge race was lost because the claim was never made. That is on
  the prompt side, and no judge can recover it.
- The v14 items that suggested the idea are 5 cases: 2 are hedged, 1
  repeats a stored bug, and 2 add a bug each.

An earlier rescore in this session put the v14 ceiling at +0.027 and
+0.058. It counted linkage-demoted items as kept and skipped the hedge
check that would have demoted them. The `j7` numbers above are correct.

## Twentieth Measurement — Field Writers in the Context Pack

**Status (2026-10-26): drafted before any code change or model call,
reviewed, and signed off with the amendments at the end. Implemented as
PROMPT_VERSION `v15-field-writers`; Step 0 recorded with three
amendments (below). Measured and not shipped: `poll_override` false
positives rose, and so did the bridge's (Results). Rolled back; the f4
code is in commit `d4beb83`.**

**Why.** Invariant-elsewhere is the largest stored false-positive class:
25 of the 51 stored false positives across the corpus's three samples
(135 runs, judged by j8). Every one is on `poll_override_90020bd`. The
claims say the worker reads `t->chans[0]` in poll mode without checking
`chan_count`, or that the attach backstop no longer covers poll mode.
Two facts in the post-state (`5ec331c`) refute them, and the reviewer
sees neither:
- `resolve_channels` builds exactly one channel whenever `?filter=` is
  set (`t->chans[0]`, `t->chan_count = 1`). `parse_query` now rejects
  `?poll=` without `?filter=`, and that rejection is in the diff. So in
  poll mode `chans[0]` is always the poll's channel.
- `chans` is declared `j2534_channel chans[QTTUNE_MAX_CHANNELS] = {}`:
  a fixed, zero-initialized array, so `chans[0]` is never out of bounds.

`resolve_channels` is unchanged by the diff, and the struct member
declaration lies outside every hunk. The fixture's pack holds two file
summaries and two typedefs, 836 characters, because the indexer
harvests C typedefs, constants and queued-connection call sites, not
C++ structs or function bodies.

**Why the pack and not the prompt.** An invariant-elsewhere claim has
the same shape as the valid removal-caused claims the last three
measurements tried to raise: "a check is gone, so this access is
unsafe". A prompt that made the reviewer doubt missing-check claims
would cut both. Only the facts tell them apart, and facts belong in the
pack.

### Design

**Change** (PACK_FORMAT_VERSION f4, PROMPT_VERSION `v15-field-writers`;
the reviewer prompt and the transcript templates are unchanged): a new
pack section, FIELD DEFINITIONS AND WRITERS, built from the index for
the members that the diff's post-change lines use:
- **Definitions:** the declaration line of each such member, from a
  `struct` or `class` defined in a modified file. This is new indexer
  work: the indexer harvests C typedefs only.
- **Writers:** each function in a modified file that assigns such a
  member and that no hunk touches. It is shown comment-free and clipped
  to a line cap. Assignments count through a pointer or object
  (`x->m =`, `x.m =`, `x->m[i] =`) and bare, inside a class's own
  methods (`m_count = 0;`, `this->m =`), each with `++`/`--` and
  compound assignment. The bare form is included so that a C++ class
  such as the bridge's is not left untreated by pattern omission.
  Coverage need not be complete.
- **Diff-authoritative, as since v6:** a function any hunk overlaps is
  never shown, because its indexed body is the pre-change version. The
  diff shows the change, and an unchanged function reads the same before
  and after it. Members only removed lines use are not looked up.
- **Caps:** the section gets its own budget of 1,800 characters inside
  `PACK_BUDGET` (6,000), with at most 3 writers of 25 lines each, and
  writers of the most-used members first. The bridge request has about
  3,500 characters of headroom (11,098 of 12,288 tokens), so the cap
  keeps every fixture under the input check.

For `poll_override` the section would show the `chans` and `chan_count`
declarations and the `resolve_channels` body. Which members and writers
each fixture gets is fixed by Step 0, below, before any model call.

**Index rebuilds:** the 7 corpus indexes are rebuilt with `--no-llm`
from throwaway clones at each `base_rev`, as before. The bridge index
(`repo_context.json`, with LLM purposes) is rebuilt from a clone at
`e0c4c31` with the summary cache, and with zero model calls. Apart from
the new harvest and `index_version`, every index must come out
identical (checked by diff).

### Step 0 (no model): render the packs

Once the code is in, every fixture's pack is rendered without a model:
the 7 corpus fixtures and the bridge. This audit is recorded here before
any sample:
- **Per fixture:** whether the section is non-empty, which decides
  whether the fixture is treated or a control; its characters; the
  whole pack's characters; and the round-1 input-check estimate.
- **Per member looked up:** the declaration found, or none.
- **Per writer-pattern hit:** the function, the member, the pattern
  form (pointer, object or bare) and the line.
- **Everything dropped, and why:** a function a hunk overlaps; the
  writer cap; the line cap; the section budget. So any truncation is
  visible before the batch.
- **A reading:** which recorded false-positive claims each section's
  content would refute, and any claim it might invite.

If the section is empty on `poll_override` or lacks `resolve_channels`,
or if any request fails the input check, the design goes back for
revision. **Any change made after seeing Step 0 is recorded here as a
dated amendment before the pilot.** Step 0 sees no model output, but its
record must show what the design was when sampling began.

### Measurement

**Samples:** fresh round-1 samples at v15, judge j8, the same
fixtures, proposals and fresh indexes:
- **Corpus:** `python -m eval_harness.corpus run --fixture all --runs
  10`, then `--fixture poll_override_90020bd --runs 10`: 80 runs, 20 of
  them on `poll_override` (decision 2).
- **Bridge:** 20 samples with the original proposal (decision 3).
- **Labels:** written before scoring, as in the nineteenth.
- **Pilot:** 3 calls first (`poll_override`, `connect_start`, bridge),
  telemetry and schema only, with the same exit as the nineteenth.

**Baselines (j8, archived v11.1 runs):**
- **`poll_override`, 9 runs:** 12 stored false positives, 1.33 per
  review, 10 of them invariant-elsewhere.
- **The other six fixtures, 57 runs:** 15 stored false positives. The
  mean of the six fixtures' rates is 0.274 (pooled: 0.263).
- **Corpus, 66 runs:** mean recall 0.413, 0.409 FPs per review.
- **Bridge, 28 samples:** 0.179 FPs per review, race 0.786, gate 0.286.

**Rule:** v15 ships if all four hold:
1. `poll_override` FPs per review fall by at least 0.5 (from 1.33 to
   0.83 or below);
2. corpus mean recall falls by at most 0.05;
3. the mean of the other six fixtures' FPs per review rises by at most
   0.05 (from 0.274);
4. bridge FPs per review rise by at most 0.05, with race and gate found
   each dropping by at most 0.15.

**How each figure is computed:**
- **Mean recall** is the mean over the 11 known bugs of each bug's
  share of its own fixture's runs. Run counts don't change it, so the
  20 `poll_override` runs weigh as the 10 did.
- **Condition 1** is `poll_override`'s own rate.
- **Condition 3** is the mean of the six fixtures' rates, so uneven run
  counts (9 or 10 per fixture in the baseline) don't weight it. It is
  one guard, not six: a bar for each 10-run fixture would fail by
  chance on most runs.
- **Pooled corpus FPs per review and valid share** are reported as
  context, not decided on. The extra `poll_override` runs weight them
  differently from the baseline.

**The bridge limit is −0.15, not the nineteenth's −0.1.** The section
probably treats the bridge too, so its race and gate rates are outcomes
here. Against the 28-run baseline, 20 runs leave a standard error of
about 0.12 on the race difference and 0.13 on the gate difference. With
no real effect, a −0.1 limit fails by chance 20% (race) and 22% (gate)
of the time; −0.15 fails 11% and 13%. Taken together, condition 4 still
fails by chance about one time in four, and a failure is read with that
in mind.

Condition 1 is the target. The other three are guards: more code in the
pack is more code to object to, and a writer body could make a valid
removal claim look covered.

**Reported apart:** invariant-elsewhere and bounds claims per fixture;
the sizes of the new sections; any claim that quotes or cites a writer
body; runaways.

**Predictions:**

| metric | prediction |
|---|---|
| Step 0: section on `poll_override` | `chans` and `chan_count` declarations plus `resolve_channels` |
| Step 0: fixtures with a non-empty section | 4–7 of 8 |
| `poll_override` FPs per review | 1.33 → 0.4–1.0 |
| `poll_override` recall (`poll_ignored`, `poll_needs_filter_at_parse`) | unchanged within 0.2 |
| corpus mean recall | 0.36–0.46 |
| other six fixtures' FPs per review (mean of fixture rates) | 0.15–0.35 |
| bridge FPs per review / race / gate | 0.10–0.30 / 0.60–0.90 / 0.15–0.45 |

**Expected by the rule:** condition 1 is a coin flip. The model has to
connect two facts, `parse_query`'s rejection in the diff and
`resolve_channels` in the pack, and the fixed array answers only the
out-of-bounds half of the claims. The guards should hold, since most
fixtures' sections will be small.

**What this cannot show:**
- **Generality.** The lever is shaped by one fixture's false positives,
  and no other corpus fixture has the class. Passing shows the lever
  removes this class here without costing anything elsewhere, not that
  it transfers. A held-out test needs a fixture where a removed or
  missing check is enforced in an unchanged function. The unused fix
  commits in the corpus notes (`ebfa918`, `1f2570b`, `b3b1487`,
  `7e9bd5e`, `839b176`) have not been checked for one.
- **The layer note.** `poll_override`'s first file is a QML comment
  change, so the reviewer gets the app layer note for a core change
  (backlog #8). That stays constant across both arms here, but it is a
  separate candidate cause of this fixture's false positives.

### Choices and review amendments (2026-10-26, before any code)

A review of the draft settled these:
- **Decision 2: 20 `poll_override` runs.** Condition 1 rests on this one
  fixture, and 10 runs against a baseline of 9 is thin.
- **Decision 3: 20 bridge runs, with the limit widened to −0.15**
  (Rule). The bridge is probably a second treated arm, not a control.
- **Aggregation is named** (Rule): condition 3 is a mean of fixture
  rates, and pooled figures are context only.
- **Writers include bare member assignments in class methods** (Design).
- **Step 0 records an audit** of sections, pattern hits and drops, and
  any later design change is an amendment (Step 0).

- **Decision 1: definitions and writers** (signed off 2026-10-26). The
  fixed array answers the out-of-bounds claims directly, and
  `bounds-fixed-array` claims on `ecu_support` have the same shape.

Every choice is now made; the draft is signed off as amended.

### Implementation and Step 0 (2026-10-26, before the pilot)

**As implemented:**
- **The indexer** (`indexer.harvest_definitions`) records two new
  things. Index keys `fields`: each struct, class and union data member,
  with its owner, comment-free declaration and line. Index key
  `functions`: each function definition that assigns a member, with its
  owner class, line span, the members it writes and the form of each
  write (pointer, object, bare, atomic), and its comment-free lines.
  A bare write is kept only in a method of the member's own class.
- **`diff_reader.old_hunk_ranges`** gives each hunk's pre-change line
  range. `read_diff` is unchanged, so the judge sees the same lines.
- **`retrieval._field_section`** builds the section under the signed-off
  caps: 8 declarations, 3 writers, 1,800 characters.
  - A writer longer than 25 lines shows its first 18 lines, an ellipsis
    line and its last 6. This rendering was chosen before Step 0, but
    with `resolve_channels` known to be 41 lines: its last line,
    `t->chan_count = n;`, carries the fact.
  - The report keeps the section's audit under `field_audit`.
- **`python -m eval_harness.corpus fields [--text]`** prints the audit
  below for every corpus fixture and the bridge, without a model.
- **Versions:** PACK_FORMAT_VERSION `f4-field-writers`, PROMPT_VERSION
  `v15-field-writers`, bridge debate fingerprint `d0a576d5de90cb90`
  (pinned).
- **Indexes:** all 8 were rebuilt from throwaway clones at their bases,
  the bridge's with the summary cache and model calls disabled. Apart
  from the two new keys and `index_version`, each is identical to the
  index it replaces. Storing function lines makes them 4–5 times larger,
  60 to 450 KB each.
- **Tests:** 218. Two mutations fail them: a writer the diff changes
  kept in the section, and the removed-code check counting every
  removed-only name.

**Step 0 audit** (`python -m eval_harness.corpus fields`):

| fixture | section | section chars | pack chars | input estimate | shown |
|---|---|---|---|---|---|
| `backoff_clamp` | empty | 0 | 518 | 2,865 | — |
| `trusted_count` | empty | 0 | 1,757 | 3,092 | — |
| `poll_override` | treated | 1,571 | 2,532 | 4,413 | 8 declarations; `resolve_channels` (24 of 41 lines) |
| `connect_start` | treated | 1,762 | 3,829 | 5,324 | 5 declarations; `applyConnectedState` (18 of 18), `SignalListModel::setSignalSet` (25 of 25) |
| `decode_length` | treated | 1,143 | 2,775 | 6,067 | 7 declarations; `toggleSubscribed` (9 of 9), `~QtTuneBridge` (10 of 10) |
| `init_noops` | treated | 1,670 | 4,415 | 6,134 | 8 declarations; `applyConnectedState` (24 of 26) |
| `ecu_support` | treated | 1,666 | 4,777 | 5,518 | 3 declarations; `disconnectSession` (24 of 33), `destroySessionLocked` (7 of 7), `setRecording` (10 of 10) |
| bridge | effectively a control | 81 | 2,768 | 11,167 | 1 declaration (`FrameSortProxy::m_newestFirst`) |

- **Every request passes the input check**, and no pack is truncated.
- **Across the 8 fixtures, 72 declarations were looked up:** 32 shown,
  36 left out because a hunk covers them, and 4 at the declaration cap
  (all on `poll_override`: the `rx_id`, `set` and `tx_id` duplicates).
- **Writer-pattern hits of the shown writers:**
  - `resolve_channels`: `chan_count` and `chans` through a pointer;
    `rx_id` and `tx_id` through an object (`t->chans[0].rx_id`).
  - `applyConnectedState` (`connect_start`): `m_session`,
    `m_linkErrorCode`, `m_errorEpisodes`, all bare.
  - `setSignalSet`: `id` and `subscribed` through an object.
  - `toggleSubscribed`: `m_subscribedCount` bare, `subscribed` through
    an object.
  - `~QtTuneBridge`: `m_session` bare.
  - `applyConnectedState` (`init_noops`): `m_connected` and
    `m_droppedFrames` atomic; `m_currentFrameCount`, `m_currentUri` and
    `m_session` bare.
  - `disconnectSession`: `m_connected` atomic; `m_errorEpisodes` and
    `m_linkErrorCode` bare.
  - `destroySessionLocked`: `m_session` bare.
  - `setRecording`: `m_recording` bare.
- **45 writers were found; 9 are shown.** Of the rest, 25 were dropped
  because the diff changes them (all 9 of the bridge's among them), and
  11 for the section budget. After the fix below, none is dropped for
  naming removed code.

**Treated and control fixtures.** `backoff_clamp` and `trusted_count` are
controls: their diffs use no member of a struct or class defined in a
modified file.

**The bridge is effectively a control, too.** The review that set its 20
runs and the −0.15 limit expected it to be a second treated fixture. It
is not: its diff changes every function that writes a member it uses, so
the section holds one declaration unrelated to the race or the gate. The
registration is unchanged. The 20 runs now check that the pack change
does not move the bridge's numbers, which is still condition 4.

**Amendments (2026-10-26, after seeing Step 0, before the pilot).** Three
implementation faults, each now pinned by a test:
1. **A default argument's braces were read as a function body.**
   `int rowCount(const QModelIndex& parent = {}) const override;` yielded
   a function `rowCount` and a data member named `override`, which then
   counted as a member use wherever `override` appears. A function head
   must now have balanced parentheses, and keywords are never member
   names.
2. **Only the first of several declarators with initializers was kept**
   (`int a = 0, b = 1;`). This was found by a unit test, not by Step 0;
   no QtTune member was affected.
3. **The removed-code check dropped `resolve_channels`**, the one writer
   the design names, because its body uses `static_cast`, which the
   diff's removed lines also use. The check now counts only names the
   index defines: types, constants, members and functions. The section
   design is otherwise unchanged.

**A reading of the sections:**
- **`poll_override`:** the section holds both refuting facts. `chans` is
  a fixed, zero-initialized array, and `resolve_channels` sets
  `chans[0]` and `n = 1` when `?filter=` is given, ending with
  `t->chan_count = n;`. Every recorded invariant-elsewhere claim rests
  on one of the two. The section says nothing about `poll_ignored`.
- **`connect_start`:** `applyConnectedState` shows the GUI thread taking
  the session (`m_session = session;`). That bears on recorded false
  positives that say `m_session` is never set (`e6c961` #1) or that
  `applyConnectedState` is missing (`2e95fa` #e2, `896c70` #e1), though
  not on where it is called. It may invite claims about the members it
  writes.
- **`decode_length` and `init_noops`:** neither section touches the
  recorded false positives, which concern the staging buffer, the
  removed include, the `void*` parameter and the removed
  `g_initialized`.
- **`ecu_support`:** the section adds writers of `m_session` without
  saying which thread runs them. The fixture's recorded false positives
  are thread-confusion claims, so it may invite more. That is condition
  3's risk.

### Pilot (2026-10-26): passes

Three records, excluded from scoring:
`measurement_round1_20261026_151439_49a62e` (`poll_override`),
`..._151617_11b8fe` (`connect_start`) and `..._151811_37d684` (bridge).
All three first attempts were accepted (`done_reason` stop): 3,422, 5,455
and 8,704 output tokens, in 99 s, 113 s and 182 s. None ran away, so the
exit (2 or more bad first attempts) is not met. Only telemetry and schema
status were read; the runner's log, which prints stored-blocker counts,
was not. The batch runs as registered.

### Results (scored 2026-10-26): not shipped

100 records, `measurement_round1_20261026_152132_e4c0d2` to
`..._181132_3d98e7` (UTC): 70 corpus samples, 10 more on
`poll_override`, then 20 bridge samples. Six corpus first attempts were
retried and are excluded:
- four `poll_override` first attempts that ran to the 12,288-token
  output cap (`c247d4`, `187a73`, `e7d68a`, `67e86a`; 42,700 to 45,500
  thinking characters);
- one `poll_override` request that failed with a CUDA out-of-memory
  error (`7a11c9`);
- one `trusted_count` reply without `questions` (`9116d9`).

That leaves 74 corpus runs (15 on `poll_override`, 9 on
`trusted_count`) and 20 bridge runs. Every item was labeled before
anything was scored (`corpus_labels.json`, sample `v15`; `labels.json`,
set `twentieth`). A test pins the corpus counts (74 runs, 103 stored, 61
valid). Both arms are judged by j8, and the v15 stored split reproduces
exactly.

| | baseline (j8, archived v11.1) | v15 | change | bar |
|---|---|---|---|---|
| 1. `poll_override` FPs per review | 1.333 (9 runs) | 1.667 (15 runs) | +0.333 | ≤ 0.83 |
| 2. corpus mean recall, stored | 0.413 | 0.430 | +0.017 | ≥ −0.05 |
| 3. other six fixtures, mean FPs per review | 0.274 | 0.283 | +0.009 | ≤ +0.05 |
| 4. bridge FPs per review | 0.179 | 0.600 | +0.421 | ≤ +0.05 |
| 4. bridge race found | 0.786 | 0.650 | −0.136 | ≥ −0.15 |
| 4. bridge gate found | 0.286 | 0.300 | +0.014 | ≥ −0.15 |
| corpus FPs per review, pooled | 0.409 | 0.568 | | context |
| corpus valid share | 64% | 59% | | context |
| recall counting demoted items | 0.588 | 0.628 | | context |
| corpus FPs per clean review | 0.389 | 0.700 | | context |

**By the rule: v15 does not ship.** Condition 1, the target, fails in
the wrong direction. Condition 4 fails on bridge false positives by
eight times its margin. Conditions 2 and 3 hold, and race and gate stay
inside the widened limit.

**Stored false positives per fixture:**

| fixture | runs | FPs per review | baseline classes | v15 classes |
|---|---|---|---|---|
| `backoff_clamp` | 10 → 10 | 0.00 → 0.00 | — | — |
| `trusted_count` | 10 → 9 | 0.00 → 0.00 | — | — |
| `poll_override` | 9 → 15 | 1.33 → 1.67 | invariant-elsewhere 10, thread 1, other 1 | invariant-elsewhere 21, thread 1, other 3 |
| `connect_start` | 10 → 10 | 0.20 → 0.00 | thread 1, deletion 1 | — |
| `decode_length` | 9 → 10 | 0.67 → 0.30 | other 4, thread 2 | thread 2, other 1 |
| `init_noops` | 9 → 10 | 0.00 → 0.10 | — | other 1 |
| `ecu_support` | 9 → 10 | 0.78 → 1.30 | thread 4, bounds 3 | thread 11, bounds 2 |
| bridge | 28 → 20 | 0.18 → 0.60 | other 5 | other 11, deletion 1 |

**Reported apart:**
- **Invariant-elsewhere** occurs only on `poll_override`: 10 claims in 9
  runs (1.11 per run), now 21 in 15 (1.40). **Bounds claims** on
  `ecu_support` went from 3 to 2 (0.33 to 0.20 per run). On
  `poll_override`, out-of-bounds claims on `chans[0]` still appear
  (`42884a` #1, `964798` #1), with the `chans[...] = {}` declaration in
  the same request.
- **A new `poll_override` shape:** `req[6]` is too small for the Mode 01
  request (2 stored, 2 hedged). `build_mode01_request` writes exactly 6
  bytes. `req` is a local, so it is not in the section.
- **Claims that cite a writer:** no `poll_override` item names
  `resolve_channels` or uses its body. Two `connect_start` items name
  `applyConnectedState`, both demoted. `9bbf58` #e2 says the call is
  missing, which is false: the section showed its body, and the
  completion lambda calls it in the post-state. `71fd74` #e2 quotes the comment that names it.
- **Sections:** as Step 0 rendered them. The `poll_override` packs hold
  the 8 declarations and `resolve_channels` (record `964798` read); the
  bridge packs hold `FrameSortProxy::m_newestFirst` alone.
- **Runaways:** 4 of 80 corpus first attempts ran to the cap, all on
  `poll_override` (4 of 20). The baseline also had 4 of 70, but spread
  across fixtures: 1 of 10 on `poll_override`. No bridge first attempt
  ran away.
- **Labels:** the bridge's `c1b3fd` #4 (`payloadHex` reads
  `data_length` unclamped) is true at `8ffbf19` but predates the diff.
  It is other-fp, as the same claim (`61e3c6` #2) was in the baseline.
  Counted as valid, the bridge rate would still be 0.55.

| prediction | predicted | observed | |
|---|---|---|---|
| Step 0: section on `poll_override` | `chans`, `chan_count`, `resolve_channels` | as predicted | HIT |
| Step 0: fixtures with a non-empty section | 4–7 of 8 | 6 (5 treated, plus the bridge's 81 characters) | HIT |
| `poll_override` FPs per review | 0.4–1.0 | 1.67 | MISSED HIGH |
| `poll_override` recall unchanged within 0.2 | — | `poll_ignored` 0.11 → 0.07; `poll_needs_filter_at_parse` 0.11 → 0.33 | MISSED (one bug) |
| corpus mean recall | 0.36–0.46 | 0.430 | HIT |
| other six fixtures' FPs per review | 0.15–0.35 | 0.283 | HIT |
| bridge FPs per review / race / gate | 0.10–0.30 / 0.60–0.90 / 0.15–0.45 | 0.60 / 0.65 / 0.30 | MISSED HIGH / HIT / HIT |
| the guards hold | — | condition 4 fails | MISSED |

**Reading:**
- **The facts reached the reviewer and did not change the claim.**
  Every `poll_override` request carried both refuting facts, and
  invariant-elsewhere claims became more frequent, not less. None cites
  `resolve_channels`. The reviewer reads a check missing from the diff
  as a defect whether or not an unchanged function in the same request
  enforces the invariant. The draft called condition 1 a coin flip
  because the model has to connect two facts; it connected neither.
  Whether naming `chans` and `chan_count` in a section made them more
  salient cannot be told from this data.
- **Thread-confusion rose where Step 0 said it might.** On
  `ecu_support` the section shows the writes of `disconnectSession`,
  whose thread start falls in the clipped middle. Claims now say
  `applyConnectedState` is "likely called from worker thread", or that
  `m_channelCount` is written from the connection thread (4 claims
  before, 11 now). Condition 3 held only because `decode_length` and
  `connect_start` fell. Step 0 found that `decode_length`'s section
  touches none of its recorded false positives, so that fall is best
  read as noise.
- **The bridge's false positives rose with an 81-character section.**
  Its section holds one unrelated declaration, so the section's content
  cannot explain 0.18 → 0.60. Of the 12 false positives, 5 are
  thread-safety claims on members other than the race's
  (`m_guiNotifyCount` twice, `m_lastReportedDropped`, `m_connected`,
  `m_droppedFrames`), and 4 are lifetime claims about `self` or the
  frame copy. Two readings, which this data cannot separate: the
  section heading ("members the changed code uses") primes member-level
  claims, or the archived baseline (v9 to v11 prompts) understates
  today's rate. The nineteenth's 9 bridge runs (v14, f3 pack) had 0.11,
  which leans toward the first. The −0.15 widening was about chance
  failures of race and gate; this failure is not one.

**Conclusion:** putting the refuting facts in the pack does not remove
invariant-elsewhere claims, and the section costs precision elsewhere.
The reviewer does not use an unchanged function to discharge a check
the diff appears to drop. The pack route for this class closes at this
design. The other candidate cause the draft named, `poll_override`'s
app layer note (backlog #8), is untested. No successor is registered.

**Rollback (2026-10-26).** v15 was committed as measured (`d4beb83`), so
the code behind the records stays in history, and then rolled back:
`reviewer_prompt.py` (PROMPT_VERSION `v11.1-critiques-feedback`, with a
history comment), `retrieval.py` (pack f3), `indexer.py`,
`diff_reader.py`, `eval_harness/corpus.py` (no `fields` audit) and all 8
indexes are as they were at `d2a7dc8`. The bridge debate fingerprint is
`8e76794ac4946aab` again (pinned), so debates send the requests the
live golden suite passed with, and the suite was not rerun. The v15
label counts stay pinned.

## Twenty-First Measurement — Per-File Layer Notes

**Status (2026-10-26): drafted before any code change or model call,
and signed off with the choices recorded at the end. The bridge control
was sampled before any code change.**

**Why.** Backlog #8: a multi-file diff gets only its first file's layer
note. `extract_file_path` returns `diff_paths(diff)[0]`, and the note
for that file's layer is the only one sent. So the reviewer is told the
wrong rules for every file in another layer. In the corpus and the
bridge, four of eight requests carry a note that is wrong for some of
their files:

| fixture | note sent today | layers of the changed files |
|---|---|---|
| `poll_override` | app (first file: a QML comment change) | app, core |
| `init_noops` | app | app, bridge, core |
| `trusted_count` | core | core, unknown (`surrogate/`) |
| bridge | bridge | bridge, app (`app/qml/Main.qml`) |
| `backoff_clamp`, `connect_start`, `decode_length`, `ecu_support` | one layer | unchanged |

On `poll_override`, every claim the invariant-elsewhere class rests on
is about `core/src/j2534_transport.cpp`, reviewed under the app note
("Qt fully permitted; focus on UI patterns, lifecycle, performance").
The twentieth measurement named this as the one untested candidate cause
of that class. It is a weak one: nothing in the app note invites a
missing-check claim, and the core note's "buffer assumptions" line may
invite bounds claims. The change is made because the input is wrong,
and measured so that a correction that costs precision or recall is
not shipped unseen.

### Design

**Change** (PROMPT_VERSION `v16-per-file-layers`; the layer notes are
prompts). When a diff's changed files fall in one layer, the note is
exactly today's, byte for byte. When they fall in two or more, the note
lists each file's layer, then each layer's rules once, strictest first
(core, bridge, app, unknown). For `poll_override`:

```
FILE LAYERS: this diff changes files in 2 layers; each file's rules apply to that file only.
- app/qml/SettingsPage.qml: app
- core/src/j2534_transport.cpp: core
FILE LAYER: core (strictest)
- NO Qt headers allowed — flag any Qt include as a blocker
- All boundary functions must use extern "C"
- Structs must be POD; handles opaque
- Buffer assumptions: 8-byte CAN vs 64+ CAN-FD
FILE LAYER: app (least restricted)
- Qt fully permitted
- Focus on UI patterns, lifecycle, performance
```

- **Paths come from `diff_reader.diff_paths`,** in diff order. A
  `--context` input without a diff keeps today's single path from a `//`
  comment line.
- **Layers come from `identify_layer`,** unchanged. Its quirks stay:
  `tests/test_bridge.cpp` is "bridge" (the substring rule), and
  `surrogate/` is unknown.
- **Records:** `inputs.layer` keeps the first file's layer, so old and
  new records compare. A new `inputs.layers` maps each path to its
  layer.
- **Fingerprint:** it hashes the map's header template and the rule
  blocks sent, never the paths, so it stays templates-only. Single-layer
  requests keep their fingerprints.
- **Sizes:** the note grows by 260 to 940 characters on the four changed
  requests (the bridge by 340, inside its ~3,500 characters of
  headroom).

### Measurement

**Only the four changed requests are sampled.** The other four are
byte-identical, which a test pins, so their archived numbers stand.
- **Samples at v16, judge j8:** `poll_override` 20 runs,
  `init_noops` 10, `trusted_count` 10, bridge 20 (original proposal).
  About 60 runs, 2.5 to 3 hours.
- **Labels** written before scoring, as in the nineteenth and twentieth.
- **Pilot:** 3 calls first (`poll_override`, `init_noops`, bridge),
  telemetry and schema only, with the same exit as the nineteenth.

**Baselines (j8, archived v11.1 runs):**
- `poll_override`, 9 runs: 1.33 FPs per review (invariant-elsewhere 10,
  thread 1, other 1); `poll_ignored` 0.11, `poll_needs_filter_at_parse`
  0.11.
- `trusted_count`, 10 runs: 0.00 FPs per review; `count_under_error`
  0.30, `static_batch_replay` 0.20.
- `init_noops`, 9 runs: 0.00 FPs per review.
- Bridge, 28 samples: 0.179 FPs per review, race 0.786, gate 0.286.

**Rule (non-inferiority: the change corrects the input, so it ships
unless it costs):** v16 ships if all three hold:
1. the mean of the three corpus fixtures' FPs per review rises by at
   most 0.15 (from 0.444);
2. the mean recall of their four known bugs falls by at most 0.10 (from
   0.180);
3. bridge FPs per review rise by at most 0.10, with race and gate found
   each dropping by at most 0.15.

`poll_override`'s invariant-elsewhere rate is reported as the
hypothesis test, not decided on.

**Predictions:**

| metric | prediction |
|---|---|
| `poll_override` FPs per review | 1.0–1.9 (no fall) |
| `poll_override` invariant-elsewhere per run | 0.9–1.6 |
| `init_noops` FPs per review | 0.0–0.4 (the core block may invite C ABI claims) |
| `trusted_count` FPs per review | 0.0–0.2 |
| mean recall of the four bugs | 0.10–0.30 |
| bridge FPs per review / race / gate | 0.10–0.40 / 0.60–0.90 / 0.15–0.45 |

**Expected by the rule:** conditions 1 and 2 hold; condition 3 is the
risk, because the twentieth's bridge rate (0.60 with a nearly empty
section) leaves it unclear whether the archived bridge baseline (v9 to
v11 prompts, 2026-10-23) is today's rate.

### Open choices

1. **Unknown files among known ones** (`trusted_count`'s
   `surrogate/`): send the unknown block ("apply all rules
   conservatively") like any other layer (recommended: one rule for
   every layer, as v10.2 chose for pathless input), or list the file as
   unknown without a block.
2. **Single-layer diffs:** keep today's note byte for byte (recommended:
   four fixtures need no samples, and every single-file debate is
   unchanged), or always send the map.
3. **A concurrent bridge control:** 20 bridge runs at v11.1, sampled
   before the code changes, as condition 3's baseline in place of the
   archived 28 (recommended: about an hour, and it also settles the
   twentieth's open reading, heading priming or a stale baseline).
   Optionally the same for `poll_override` (20 runs, another hour).
4. **Bars and run counts** as drafted, or changed.

### Choice 3 and the bridge control (2026-10-26, before any sample)

**Choice 3 decided: a concurrent bridge control.** 20 bridge round-1
samples at v11.1 (fingerprint `8e76794ac4946aab`, the tree at
`eb10006`), with the original proposal and judge j8, sampled before any
code change and labeled before scoring by the same rules. They replace
the archived 28 as condition 3's baseline: v16's bridge FPs per review
may rise by at most 0.10 over the control's, and race and gate found may
each drop by at most 0.15 from the control's. The archived baseline is
reported as context. No `poll_override` control.

**Prediction for the control:** FPs per review 0.10–0.40, race
0.60–0.90, gate 0.15–0.45.

**What the control also reads.** The twentieth's bridge rate (0.60 with
a one-declaration section) had two readings: the section heading
primes member-level claims, or the archived baseline understates
today's rate. A control near 0.18 favors the first; one near 0.60
favors the second. That reading is recorded with the control's
results; it changes nothing about the twentieth, which stays not
shipped.

**Choices 1, 2 and 4 decided (2026-10-26, before any v16 code):** a
file in no known layer sends the unknown block like any other layer;
single-layer diffs keep today's note byte for byte; bars and run counts
as drafted. The draft is signed off as amended.

### Control results (scored 2026-10-26, before any v16 sample)

20 records, `measurement_round1_20261026_191304_72dbd8` to
`..._195825_962e76` (UTC), all stamped v11.1 with fingerprint
`8e76794ac4946aab` and judge j8. One, `e9c923`, ran to the output cap
on all three attempts and failed closed (`AGENT_FAILURE`): the first
bridge record on file whose retries never recovered. It is excluded,
leaving 19 runs. Every item was labeled before scoring (`labels.json`,
set `control21`).

| | archived (28) | control (19) | prediction | |
|---|---|---|---|---|
| FPs per review | 0.179 | 0.105 | 0.10–0.40 | HIT |
| race found | 0.786 | 0.526 | 0.60–0.90 | MISSED LOW |
| gate found | 0.286 | 0.421 | 0.15–0.45 | HIT |

Of 32 kept blockers, 30 are valid (18 race, 12 gate); the two false
positives are the dangling-copy claims (`228951`). Condition 3's bars
are now: v16 bridge FPs per review at most 0.205, race found at least
0.376, gate found at least 0.271.

**Reading:**
- **The twentieth's bridge rise came with its section, not from a stale
  baseline.** Today's v11.1 rate (0.11) is as low as the archived one
  (0.18), against v15's 0.60.
- **The archived race rate overstates today's.** Race found 0.53 here,
  0.79 in the archive. Against this control the nineteenth's bridge race
  (0.556) would not have read as a drop. That does not change the
  nineteenth's verdict, which failed on recall as well, but bridge race
  comparisons against the archived 28 should be read with this in mind.
  Gate moved the other way (0.29 → 0.42), so attention between the two
  shifts from sample to sample.

### Implementation (2026-10-26, while the control sampled)

- **`file_metadata.layer_note_for(paths)`** returns the note and its
  template (the note without its paths). `LAYER_ORDER` and
  `LAYER_MAP_HEADER` are new. `debate._prepare` passes every path from
  `diff_paths`, or the one path from a `//` comment line when there is
  no diff. `_Setup` gains `layers` and `layer_template`; records gain
  `inputs.layers`; the fingerprint hashes `layer_template` in place of
  the note.
- **Versions:** PROMPT_VERSION `v16-per-file-layers`. Fingerprints:
  bridge `dbb1ed45156230be` (was `8e76794ac4946aab`), `poll_override`
  `a4f16eec8e5e6729`, `init_noops` `ffc5acdd20a814dd`, `trusted_count`
  `3b8cd7fc10523092`. The four single-layer fixtures keep theirs.
- **Byte check:** the reviewer system prompt and static transcript
  section of all eight fixtures were compared with a worktree at
  `eb10006`: the four single-layer fixtures are identical, the four
  multi-layer ones changed, as planned.
- **Input check** at v16: `trusted_count` 3,111, `poll_override` 3,905,
  `init_noops` 5,798 and the bridge 11,193 estimated tokens, all under
  12,288.
- **Tests:** 207. Sending only the first file's note again fails two of
  them.

The edits did not reach the running control: its process had loaded
the v11.1 modules before they were made, and its records carry v11.1's
version and fingerprint (checked when it finishes).

### Pilot (2026-10-26): passes

Three records, excluded from scoring:
`measurement_round1_20261026_200203_679fc3` (`poll_override`),
`..._200452_f6d34e` (`init_noops`) and `..._200527_ce8a35` (bridge). Each
carries v16's fingerprint for its fixture and the expected
`inputs.layers`. All three first attempts were accepted (`done_reason`
stop): 8,629, 1,293 and 1,415 output tokens, in 169 s, 34 s and 34 s. None
ran away, so the exit is not met. Only telemetry, stamps and schema
status were read. The batch runs as registered.

### Results (scored 2026-10-26): not shipped

60 records, `measurement_round1_20261026_200617_180332` to
`..._220806_b94a4e` (UTC): 20 `poll_override`, 10 `init_noops`, 10
`trusted_count`, then 20 bridge samples, every one stamped
`v16-per-file-layers` with its fixture's expected fingerprint. Four first
attempts ran to the 12,288-token output cap (`1f7900` on
`poll_override`, `78f09a` on `init_noops`, `8f74e3` and `9747cc` on the
bridge). Three recovered on retry and are excluded. `9747cc` ran to the
cap on all three attempts and failed closed, as the control's `e9c923`
did. That leaves 38 corpus runs (19 `poll_override`, 9 `init_noops`, 10
`trusted_count`) and 18 bridge runs. Every item was labeled before
anything was scored (`corpus_labels.json`, sample `v16`; `labels.json`,
set `twentyfirst`). A test pins the corpus counts (38 runs, 31 stored, 6
valid). Both arms are judged by j8, and the stored split reproduces
exactly.

| | baseline | v16 | change | bar |
|---|---|---|---|---|
| 1. mean FPs per review, three fixtures | 0.444 | 0.478 | +0.034 | ≤ +0.15 |
| 2. mean recall, four bugs | 0.181 | 0.126 | −0.054 | ≥ −0.10 |
| 3. bridge FPs per review (control) | 0.105 | 0.333 | +0.228 | ≤ 0.205 |
| 3. bridge race found (control) | 0.526 | 0.556 | +0.029 | ≥ 0.376 |
| 3. bridge gate found (control) | 0.421 | 0.500 | +0.079 | ≥ 0.271 |
| recall counting demoted items | 0.533 | 0.503 | | context |
| bridge valid share | 94% | 82% | | context |

The corpus baseline is the archived v11.1 runs under j8 (the registered
0.180 is 0.1806 rounded); the bridge baseline is the control.

**By the rule: v16 does not ship.** Conditions 1 and 2 hold. Condition 3
fails on bridge false positives: 6 in 18 runs against the control's 2 in
19. Race and gate both clear their bars.

**Per fixture:**

| fixture | runs | FPs per review | recall (stored) | classes |
|---|---|---|---|---|
| `poll_override` | 9 → 19 | 1.33 → 1.21 | `poll_ignored` 0.11 → 0.05, `poll_needs_filter_at_parse` 0.11 → 0.05 | invariant-elsewhere 10 → 20, thread 1 → 2, other 1 → 1 |
| `init_noops` | 9 → 9 | 0.00 → 0.22 | — | other 0 → 2 (one run) |
| `trusted_count` | 10 → 10 | 0.00 → 0.00 | `count_under_error` 0.30 → 0.10, `static_batch_replay` 0.20 → 0.30 | — |
| bridge | 19 → 18 | 0.11 → 0.33 | race 0.53 → 0.56, gate 0.42 → 0.50 | other 2 → 1, removal-objection 0 → 4, deletion 0 → 1 |

**Reported apart:**
- **The hypothesis test: invariant-elsewhere on `poll_override`** went
  from 1.11 to 1.05 stored claims per run (1.67 to 1.26 counting
  demoted items). The core block reached every `poll_override` request,
  and the missing-channel and `chans[0]` claims are unchanged in form.
- **The bridge's false positives are concentrated.** 4 of the 6 come
  from one run (`559651`). It listed the removed LiveView members
  (the batching timer, `signalBatchCount`, `signalModel`) as blockers,
  each quoting a post-change header line, so the evidence check kept
  them. The other 17 runs have 2 (`fd1e6b` #4 on `m_droppedFrames`,
  `aed765` #1, which says `Main.qml` still uses `signalModel`). The rule
  counts runs; the bar stands as registered.
- **Where the bridge's false claims moved.** Counting stored and demoted
  items, false claims are about as many as in the control (16 against
  15), but their classes shifted. Removal objections rose from 2 to 9
  and deletion claims fell from 11 to 5, and items that name QML or the
  bridge's QML-facing API rose from 1 to 7 (in 5 runs). The v16 bridge
  request names `app/qml/Main.qml` and adds the app block ("Focus on UI
  patterns, lifecycle, performance").
- **`count_under_error`** fell in stored recall (3 runs to 1) while
  claims about it, counting demoted items, held at 9 of 10 runs: its
  claims still quote the removed call.
- **Runaways:** 4 of 60 first attempts (7%), against about 5% on record.
  The bridge's two failed-closed records (`e9c923`, `9747cc`) are the
  first on file, both today, one under each prompt (9,703 and 9,800
  prompt tokens), so they are not v16's doing.

| prediction | predicted | observed | |
|---|---|---|---|
| `poll_override` FPs per review | 1.0–1.9 | 1.21 | HIT |
| `poll_override` invariant-elsewhere per run | 0.9–1.6 | 1.05 | HIT |
| `init_noops` FPs per review | 0.0–0.4 | 0.22 | HIT |
| `trusted_count` FPs per review | 0.0–0.2 | 0.00 | HIT |
| mean recall of the four bugs | 0.10–0.30 | 0.126 | HIT |
| bridge FPs per review / race / gate | 0.10–0.40 / 0.60–0.90 / 0.15–0.45 | 0.33 / 0.56 / 0.50 | HIT / MISSED LOW / MISSED HIGH |
| conditions 1 and 2 hold, 3 is the risk | — | 1 and 2 hold, 3 fails | HIT |

**Reading:**
- **The layer note is not what drives invariant-elsewhere.** With the
  core rules on the core file, the class held its rate. Both candidate
  causes the twentieth named, missing facts and the wrong layer note,
  are now tested, and neither moves it. What is left is the model's own
  reading of a dropped check as a defect.
- **Naming a file directs attention to it.** The map and the app block
  are the only changes in the bridge request. The bridge claims shifted
  toward the removed UI feature, and some of those quote post-change
  lines that the evidence check accepts. One run carries most of the
  rise, so the size is uncertain; its direction matches the class
  shift across the other runs.
- **Recall moved within its margin** and mostly through the quote rule
  (`count_under_error` is still claimed, but its claims are demoted).

**Conclusion:** the correct per-file note costs bridge precision beyond
the registered margin and does not change the target class. Backlog #8
stays open as a known limitation. No successor is registered.

**Rollback (2026-10-26).** v16 was committed as measured (`56252be`),
so the code behind the records stays in history, and then rolled back:
`file_metadata.py`, `debate.py` and `reviewer_prompt.py` (PROMPT_VERSION
`v11.1-critiques-feedback`, with a history comment) are as they were at
`eb10006`. The bridge debate fingerprint is `8e76794ac4946aab` again
(pinned), and `poll_override`'s matches its archived v11.1 records, so
debates send the requests the live golden suite passed with; the suite
was not rerun. The v16 label counts stay pinned.

## Runaway Diagnostic — Do Runaways Repeat?

**Status (2026-10-26): closed. A diagnostic for backlog #19, not a ship decision.
Predictions written after the collection run started and before any of
its output was read.**

**Why.** About 6% of reviewer first attempts think until the
12,288-token cap (29 of 458 on record), take a median 266 s against 83 s
for an accepted reply, and twice on 2026-10-26 failed all three
attempts. #19 proposes streaming the reply and aborting when the
thinking repeats. Two things are known without a model:
- **The 74 runaway tails on record show no verbatim loop.** They keep
  400 characters; the longest repeat in most is 10 to 37 characters,
  usually a quoted code fragment. 76 of 77 runaways never began the
  reply.
- **A lower cap is not the abort.** Accepted reviewer replies run
  continuously up to the cap: 10.7% exceed 8,192 tokens, and the
  longest used 12,248.

**Collection.** Since this change, `agent_client` keeps the whole
thinking of any attempt that hits the cap or runs past 8,192 tokens
(`LONG_THINKING_TOKENS`); requests are unchanged (bridge fingerprint
`8e76794ac4946aab`). The run:
- `eval_harness.runaway repro` re-sends the control's `e9c923` attempt 1
  twice (v11.1, bridge, the JSON correction, temperature 0.05; both of
  its retries ran away), checked byte for byte against the record's
  sizes;
- 20 `poll_override` round-1 runs at v11.1, for long accepted replies
  (the control) and any new runaway.

**Measure** (`eval_harness.runaway`): the share of 12-word shingles in
the thinking's prose that already occurred earlier, overall and by
thirds; the longest repeated run; quoted code (``` fences) apart.

**Predictions:**

| | prediction |
|---|---|
| `e9c923` re-sends that run away again | 1–2 of 2 |
| runaways' prose repeat share | below 0.15: an open-ended search, not a loop |
| runaways' code repeat share | above their prose share (the diff re-quoted) |
| long accepted replies' prose repeat share | overlaps the runaways' |

**Decision rule for #19's next step:** a repetition abort is worth
building and measuring only if a threshold on the last third's prose
repeat share separates every runaway from every long accepted reply in
this data. Otherwise #19 records that the reviewer's runaways are not
loops and turns to their cost, not their detection.

### Results (2026-10-26)

The run took 72 minutes: the two re-sends (records
`measurement_runaway_20261026_224408_1cb3fd` and `_225030_e962c2`),
then 20 `poll_override` runs (`measurement_round1_20261026_225032_17a355`
to `_234601_0e61c1`). Nine attempts kept their whole thinking: three
runaways and six accepted replies past 8,192 tokens.

| record | attempt | tokens | end | prose repeat | by third | longest (words) | code repeat |
|---|---|---|---|---|---|---|---|
| e962c2 (re-send) | 1, at 0.05 | 12,288 | cap | 0.152 | 0.01 / 0.08 / 0.36 | 196 | 0.396 |
| 17a355 | 0, at 0.7 | 12,288 | cap | 0.020 | 0.01 / 0.03 / 0.02 | 23 | 0.286 |
| 6cb4e4 | 0, at 0.7 | 12,288 | cap | 0.012 | 0.00 / 0.01 / 0.03 | 28 | 0.193 |
| 242fb1 | 0 | 8,983 | ok | 0.006 | 0.00 / 0.00 / 0.02 | 20 | 0.315 |
| f4711d | 0 | 10,487 | ok | 0.008 | 0.00 / 0.01 / 0.02 | 31 | 0.284 |
| 2bf401 | 0 | 10,265 | ok | 0.063 | 0.02 / 0.06 / 0.11 | 41 | 0.188 |
| dbb036 | 0 | 10,350 | ok | 0.033 | 0.01 / 0.03 / 0.06 | 31 | 0.327 |
| 660eaa | 0 | 10,798 | ok | 0.026 | 0.01 / 0.02 / 0.05 | 30 | 0.306 |
| 0e61c1 | 0 | 12,228 | ok | 0.013 | 0.00 / 0.01 / 0.03 | 26 | 0.341 |

| | prediction | result | |
|---|---|---|---|
| `e9c923` re-sends that run away again | 1–2 of 2 | 1 of 2 (the other accepted in 3,173 tokens, 108 s) | HIT |
| runaways' prose repeat share | below 0.15 | 0.020 and 0.012; the re-send 0.152 | MISSED for 1 of 3 |
| runaways' code repeat share | above their prose share | above in all 3 (and in all 9) | HIT |
| long accepted replies' prose repeat share | overlaps the runaways' | 0.006–0.063 against 0.012–0.152 | HIT |

**Decision rule: no threshold separates them.** On the last third's
prose repeat share, two runaways (0.02, 0.03) sit below four of the six
long accepted replies (up to 0.11). #19's repetition abort is not built.

**Two kinds of runaway.**
- **The re-send is a loop.** At temperature 0.05, after the JSON
  correction, the model walked the diff, reached its two findings (the
  removed in-flight counter and the `MaxFrames` race), then started the
  walk again: a 196-word passage of its own prose recurs verbatim, and
  "Now let me think about the verdict" appears twice. It ended
  re-quoting QML hunks.
- **The two first-attempt runaways are indecision, not repetition.**
  Both at temperature 0.7 on `poll_override`. Each reaches a conclusion
  ("I don't see any clear violations"; "OK, I think I've gone deep
  enough. Let me write my analysis.") and reopens it ("However, I do see
  one potential issue"; "Actually, let me re-read the rules one more
  time"), on a different question each time: thread safety, the request
  buffer's size, `chans[0]` with no channel, scheduler and poll modes
  both active. No passage repeats.
- One loop in three is too few to say that loops belong to retries at
  low temperature; the archived tails cannot tell, since all but one
  never began the reply.

**Cost.** The two `poll_override` runaways took 586 s of the batch's
3,618 s of reviewer time (16%); both retries recovered, in 21 s and
9 s. Over the 20 runs, 2 first attempts ran away (10%; 6.3% over the
458 on record). The loss that matters is the failed-closed sample:
`e9c923`'s retry ran away again on one of two re-sends, so a retry at
0.05 is no guarantee on that input.

**What #19 becomes.** Not detection by repetition. Open, not
registered: the cost side, for example a first attempt whose
wall-clock or token budget below the cap triggers an early retry, which
would have to be weighed against the 10.7% of accepted replies that run
past 8,192 tokens.

### Amendment (2026-10-26): the cost side, offline

Not registered in advance: a descriptive check of the early retry #19
named as its open option, from telemetry already on record, with no
model call. Population: the 398 round-1 measurement records whose
reviewer telemetry has token counts. 18 first attempts (4.5%) ran to the
cap; 18 retries followed them (16 accepted, median 14 s; 2 ran away
again), and 2 calls failed every attempt. Attempts at the cap took
1.74 h of the 12.6 h of reviewer time (13.8%), the most any abort could
save.

The policy: cut a first attempt at T tokens and retry. Time at T is
estimated as the attempt's wall time scaled by T over its token count;
a cut accepted reply costs a retry at the median accepted retry's 14 s
(at the mean of all retries, 70 s, no budget saves more than 0.4%).
Lost findings are counted on the hand-labeled corpus first attempts
(178 valid and 143 false stored blockers):

| T (tokens) | time saved | accepted replies cut | valid blockers lost | false blockers lost |
|---|---|---|---|---|
| 6,144 | 13.1% | 108 (28.5%) | 59 of 178 | 42 of 143 |
| 8,192 | 6.1% | 47 (12.4%) | 25 of 178 | 15 of 143 |
| 10,240 | 2.2% | 18 (4.7%) | 9 of 178 | 6 of 143 |
| 11,264 | 0.9% | 9 (2.4%) | 7 of 178 | 2 of 143 |

Long replies are not worse: labeled replies of 8,192–10,240 tokens carry
1.00 valid blockers each, against 0.65–0.67 below 8,192. Every budget
that saves real time cuts more valid findings than false ones, and the
replies that replace them are retries, the short mode the scorers
exclude. **An early retry on a token or time budget is not worth
building.** What remains of #19 is the failed-closed call (2 of 398),
where the retries run away too.

## Twenty-Second Measurement — Reviewer Model Bake-Off

**Status (2026-10-27): closed, no candidate ships.
`nemotron-3.5-lightning:30b` was dropped at Stage 0 (runs to the cap);
`qwen3-coder:30b` fails condition 1 in Stage 1 (mean recall 0.091
against the control's 0.423). `laguna-xs-2.1` stays the reviewer.**

**Why.** Five levers in a row changed what the reviewer is sent or how
its reply is judged, and none shipped (seventeenth to twenty-first
measurements, the runaway diagnostic). Several readings point at the
model: in the eighteenth it declined its own valid claims as readily as
its false ones, most runaways reopen their own conclusion, and voting
failed on the corpus because the model repeats its false positives. The
reviewer model itself has not been varied since ADR-0001, which chose
it on header probes before the corpus existed.

**Arms** (all local, all on Ollama 0.40.4; digests recorded at pull,
before Stage 0):
- **Control:** `laguna-xs-2.1` (33B mixture of experts, 3B active),
  sampled in the same window.
- `qwen3-coder:30b` (30B mixture of experts, 3B active, 19 GB): a
  coding model, the same size class as the control, no thinking mode.
- `nemotron-3.5-lightning:30b` (30B mixture of experts, 3B active):
  newer, built for agents, thinking mode.

Everything else is today's: prompt v11.1 (fingerprints unchanged; the
fingerprint hashes templates, not the model), judge j8, `NUM_CTX` 24576,
`NUM_PREDICT` 12288, temperature 0.7 on first attempts and 0.05 on
retries. No `think` option is sent, so each model thinks as its Ollama
default does. A run selects the model with `--reviewer-model`, which
every record stamps under `models_used`. The prompt was developed on
the control, which favors it; that bias is accepted, not corrected.

**Stage 0, per candidate** (3 round-1 runs on the bridge fixture;
telemetry and schema only, blockers not read; excluded from scoring).
A candidate is dropped if 2 or more of its 3 first attempts are unusable
(no schema-valid JSON, or at the cap), or if its accepted first attempts
take a median above 276 s, three times the control's 92 s over 379
archived round-1 first attempts.

**Stage 1:** `corpus run --fixture all --runs 5` per arm (35 samples
each), the control first, then each surviving candidate. Every item of
every arm is labeled in `corpus_labels.json` before any arm is scored,
by the existing rules; the labels are not blind (records name their
model), so each new judgment call is written in the label notes.

**Measures** (j8 via replay, first attempts): mean recall (the mean of
the 11 known bugs' per-fixture rates), false positives per review,
valid share of stored blockers, false positives per clean review;
first attempts at the cap, calls that fail closed, and median wall time
of a first attempt.

**Rule.** A candidate replaces the control only if all of these hold:
1. **Better on the corpus** against the concurrent control: mean recall
   up at least 0.10 with false positives per review up at most 0.05;
   or false positives per review at most 0.7 times the control's with
   mean recall down at most 0.05.
2. **Practical:** median first-attempt wall time at most twice the
   control's, and at most 1 of its 35 calls fails closed.
3. **Confirmed** (two candidates make one chance pass likely enough to
   check): a fresh 35-run corpus sample of the candidate passes
   condition 1 against the same control; 20 bridge runs, labeled, hold
   the twenty-first's bars (false positives per review at most 0.205,
   race at least 0.376, gate at least 0.271); the golden suite passes
   10/10.

A candidate that ships changes `MODELS["code_reviewer"]` and gets an
ADR-0001 amendment.

**Exploratory, no ship rule: two models as corroboration.** Runs are
paired by order within a fixture (the control's run i with the
candidate's run i). A stored blocker is corroborated when the paired
run of the other model has a stored blocker quoting the same hunk of
the same file. Reported: false positives per review and mean recall of
the control's corroborated blockers alone, and of the union of both
models' stored blockers. A result worth having becomes its own
registered measurement.

**Predictions:**

| | prediction |
|---|---|
| `qwen3-coder:30b` Stage 0 | passes; median wall below the control's, no runaways |
| `nemotron-3.5-lightning:30b` Stage 0 | passes |
| `qwen3-coder:30b` corpus | recall below the control's; false positives within ±0.15 per review; fails condition 1 |
| `nemotron-3.5-lightning:30b` corpus | recall below the control's and false positives above; fails condition 1 |
| any candidate ships | no |
| corroboration (exploratory) | false positives per review fall by 30% or more and mean recall by 0.10 or more |

**Cost:** about 1.5–3 h of GPU per arm (4.5–9 h in all) and about 35
records to label per arm.

### Models (2026-10-26, recorded at pull, before Stage 0)

Ollama 0.40.4, digests from `/api/tags`:

| model | digest | size | quantization | parameters |
|---|---|---|---|---|
| `laguna-xs-2.1:latest` (control, unchanged) | `0175be1e57f44bb4a96779d1840dbadd84399ab87bf70688c321ecadeadd757f` | 20.3 GB | Q4_K_M | 33.4B |
| `qwen3-coder:30b` | `06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca` | 18.6 GB | Q4_K_M | 30.5B |
| `nemotron-3.5-lightning:30b` | `e6905fffe2e2d9bbe325a9a2d2e074e3bd32683721bc6dfba409dede2f17f4dc` | 25.4 GB | Q4_K_M | 32.9B |

Ollama reports nemotron at 32.9B parameters, not the 30B its tag
suggests, and 25.4 GB, the largest of the three; on the 12 GB card more
of it runs on the CPU than the control does, which Stage 0's time limit
covers.

### Stage 0 (2026-10-26): `qwen3-coder:30b` passes, `nemotron-3.5-lightning:30b` is dropped

Six bridge runs, excluded from scoring. Each candidate's first attempts:

| record | model | first attempt | wall | prompt / output tokens | thinking chars |
|---|---|---|---|---|---|
| `20261027_032412_71be42` | `qwen3-coder:30b` | accepted | 43 s | 8,755 / 466 | 0 |
| `20261027_032455_b83fb7` | `qwen3-coder:30b` | accepted | 13 s | 8,755 / 425 | 0 |
| `20261027_032508_f4ad3a` | `qwen3-coder:30b` | accepted | 10 s | 8,755 / 299 | 0 |
| `20261027_032519_aed591` | `nemotron-3.5-lightning:30b` | at the cap | 362 s | 9,283 / 12,288 | 48,388 |
| `20261027_034101_b6acbe` | `nemotron-3.5-lightning:30b` | at the cap | 496 s | 9,283 / 12,288 | 50,086 |
| `20261027_040233_9f9587` | `nemotron-3.5-lightning:30b` | at the cap | 297 s | 9,283 / 12,288 | 47,468 |

- **`qwen3-coder:30b` passes:** 0 of 3 unusable, median 13 s (limit
  276 s). It does not think, as predicted.
- **`nemotron-3.5-lightning:30b` is dropped:** 3 of 3 first attempts
  ran to the cap, and all three records failed closed. Of the 6 retries,
  one was accepted (in `aed591`, 10,733 tokens) but lacked the
  `questions` key, three more ran to the cap, and two timed out at
  600 s. The runaway profile (`eval_harness.runaway`) finds no loop:
  the repeated share of the last third is at most 0.06, with 12 to 18
  re-checks per thousand words. This is the indecision seen in laguna's
  runaways, not repetition. Its prediction ("passes") missed.

The runner prints each record's stored blocker count, and those lines
were seen: 0, 0, 0 for `qwen3-coder:30b`. The bridge's race and gate
were never read, and the count does not enter any condition. It is
recorded here because it bears on the corpus prediction for qwen.

Stage 1 is the control and `qwen3-coder:30b`, 35 runs each.

### Amendment (2026-10-27, before Stage 1): the qwen prediction, sharpened by Stage 0

In Stage 0, qwen stored 0 blockers in each of its 3 bridge runs. The
control stored none in 5 of the twenty-first's 19 control runs (0.26),
so at the control's rate three empty runs would happen about 2% of the
time (0.26³ ≈ 0.018). The prediction is now: qwen's corpus mean recall
falls 0.10 or more below the control's, and qwen fails both branches of
condition 1. The rule is unchanged. More bridge runs were considered and
not added: Stage 1 is scored on the corpus, and the bridge enters only
the confirmation step, which qwen reaches only by passing condition 1.

### Stage 1 results (scored 2026-10-27): `qwen3-coder:30b` fails condition 1

Records `measurement_round1_20261027_131621` to `_142652` (control) and
`_142922` to `_143555` (qwen), 35 each, sampled back to back. The
control's `120882` ran to the cap on its first attempt and was accepted
on a retry, so it is excluded. Every item was labeled in
`corpus_labels.json` (samples `b22_laguna` and `b22_qwen`) before either
arm was scored. The labels are not blind; the judgment calls are in the
note `b22_twenty_second`. Scored with judge j8 (`replay --corpus`
reproduces the stored split in both arms):

| | `laguna-xs-2.1` (control) | `qwen3-coder:30b` |
|---|---|---|
| runs scored | 34 | 35 |
| stored blockers | 37 | 7 |
| valid share | 65% | 100% |
| false positives per review | 0.382 | 0.000 |
| false positives per clean review | 0.30 | 0.00 |
| mean recall, stored | 0.423 | 0.091 |
| mean recall, any item | 0.632 | 0.091 |
| runs with a stored blocker | 19 of 34 | 5 of 35 |
| first attempts at the cap | 1 of 35 | 0 of 35 |
| calls failed closed | 0 | 0 |
| median first-attempt wall | 67 s | 11 s |

The control matches the archived v11.1 corpus sample (66 runs: recall
0.413, 0.409 false positives per review, 64% valid), so the window was
not unusual.

**Rule.** Condition 1 fails on both branches. Recall is 0.332 below
the control's (the first branch needs +0.10). False positives are well
under 0.7 times the control's (0.267), but recall falls by more than
0.05. Condition 2 holds (11 s against a 134 s limit, none failed
closed) but does not matter. No confirmation sample was run.

**Reading.** qwen is precise and close to silent. Of its 35 runs, 30
stored nothing, and only one of those raised a demoted item (a false
bounds claim on `ecu_support_7d297b4`, hedge-demoted). All of its
stored blockers are on `decode_length_b47687c`: the hardcoded 8-byte
decode length in 5 of 5 runs, plus the `void*` `setSignalSet`
(unlisted) twice. That defect is visible on one post-change line. qwen
found none of the bugs that need the removed lines read against the
code that remains (the trusted-count helper, the poll override, the
connect handoff, the dropped drop reports). The control stores most of
those; the trusted-count pair it finds only as evidence-demoted items.

| prediction | outcome |
|---|---|
| `qwen3-coder:30b` Stage 0: passes, median below the control's, no runaways | held |
| `nemotron-3.5-lightning:30b` Stage 0: passes | missed: dropped |
| `qwen3-coder:30b` corpus, as amended: recall 0.10 or more below the control's, fails both branches | held: −0.332, fails both |
| `qwen3-coder:30b` corpus, as first registered: recall below, false positives within ±0.15 per review, fails condition 1 | recall and condition 1 held; false positives missed (−0.382) |
| `nemotron-3.5-lightning:30b` corpus | not run |
| any candidate ships | held: none |
| corroboration: false positives fall 30% or more, mean recall 0.10 or more | held: 0.382 → 0.029 (−92%), 0.423 → 0.136 |

**Corroboration (exploratory).** There are 34 pairs; the retried
control run drops its pair. Only `decode_length_b47687c` has
corroborated control blockers: the decode length in 4 of 4 pairs, and
`staging_clear_per_frame` in 2. Those 2 count only because `clear()`
shares the decode line's hunk, not because qwen raised it. The union
of both models' stored blockers equals the control's own numbers (0.382
and 0.423): qwen found no bug that its paired control run missed. With
this candidate, corroboration comes down to keeping one fixture's
blockers, so nothing is registered.

`MODELS["code_reviewer"]` stays `laguna-xs-2.1`; ADR-0001 is not
amended.

## Twenty-Third Measurement — Engineer Model Bake-Off

**Status (2026-10-27): not shipped. `gpt-oss:20b` passes condition 1
(mean recall in any item 0.741 against gemma's 0.509) and fails
condition 2 (0.242 false engineer blockers per review, bar 0.10).
`gemma4:12b` stays the engineer.**

**Why.** The engineer (`gemma4:12b`, the "senior automotive engineer"
prompt) is the debate's domain expert, and its output has never been
measured. It matters to the verdict in one way: an engineer blocker,
which only the hedge check filters (there is no evidence check for the
engineer), forces a reject. In the 27 archived round-1 engineer replies
(all on the bridge fixture) gemma raised no blocker at all, about two
concerns and two questions per reply, in a median 49 s; it raised the
removed backpressure gate as a concern. The question is whether another
local model, in the same role with the same prompt, finds more of the
known bugs without raising false blockers.

**Arms:** `gemma4:12b` (control, sampled in the same window) and
`gpt-oss:20b` (21B mixture of experts, about 3.6B active, 14 GB, a
reasoning model). Same prompt (`AUTO_ENGINEER_PROMPT`, v11.1), same
settings as the reviewer bake-off; no `think` option is sent.

**The mode** (`corpus run --engineer [--engineer-model NAME]`,
`debate.run_round1_engineer`): the engineer's round-1 call alone, on the
transcript a debate's round 1 sends it. Within a round the engineer
never sees the reviewer, so this is the same call a debate makes; a test
pins the request to a debate's, and debate requests are byte-identical
before and after the refactor that shares the call. Records are
`coach_artifacts/measurement_engineer_<id>.json`.

**Stage 0:** 3 `gpt-oss:20b` runs on `poll_override_90020bd`, telemetry
and schema only, excluded from scoring. It is dropped if 2 or more of
its 3 first attempts are unusable, or if its accepted first attempts
take a median above 150 s (three times gemma's 49 s).

**Stage 1:** 35 runs per arm (`--fixture all --runs 5`), the control
first. Labels (`eval_harness/engineer_labels.json`, scored by
`corpus score`), written before either arm is scored: every engineer
blocker gets a class (a known bug, `unlisted`, or a false class); a
concern or question is labeled only when it states a known bug's
defect, by the rules the reviewer labels use.

**Measures** (first attempts): false engineer blockers per review;
wrong rejects, meaning runs on the two clean fixtures with any engineer
blocker; mean recall over the 11 known bugs, in blockers and in any
item (blockers, concerns, questions); median wall time, calls at the
cap, calls that fail closed.

**Rule.** `gpt-oss:20b` replaces gemma as the engineer only if all of
these hold:
1. mean recall in any item at least 0.10 above the control's;
2. at most 0.10 false engineer blockers per review, and at most 1 wrong
   reject in its 10 clean-fixture runs;
3. median first-attempt wall time at most 180 s, and at most 1 of 35
   calls failing closed;
4. confirmed by a fresh 35-run sample that again meets conditions 1 and 2.

What a better engineer buys is limited and stated here: its blockers
can reject, and its concerns and questions reach the reviewer in round
2's CRITIQUES section and the reader in the verdict's open questions.
How a different engineer changes later rounds is not measured.

**Predictions:**

| | prediction |
|---|---|
| gemma (control) | no engineer blockers, as in the 27 archived replies; recall in any item 0.2–0.4 |
| `gpt-oss:20b` Stage 0 | passes |
| `gpt-oss:20b` blockers | raised in at least 20% of runs |
| `gpt-oss:20b` recall in any item | at least 0.10 above gemma's (condition 1 holds) |
| `gpt-oss:20b` false blockers | above 0.10 per review (condition 2 fails) |
| ships | no |

**Cost:** about 0.5 h of GPU for the control and 1–1.5 h for
`gpt-oss:20b`; labeling about 35 records per arm, mostly blockers.

### Models (2026-10-26, recorded at pull, before Stage 0)

Ollama 0.40.4, digests from `/api/tags`:

| model | digest | size | quantization | parameters |
|---|---|---|---|---|
| `gemma4:12b` (control, unchanged) | `6114515d63c17436a7c0417d82820ac65ad643e2806c5a3c89cb62846436ed0b` | 8.0 GB | Q4_K_M | 11.9B |
| `gpt-oss:20b` | `f38aa0c53da5f8c49d08c43a99df24ff53167fe68e24664a7777288e7656fdfe` | 13.8 GB | MXFP4 | 20.9B |

### Stage 0 (2026-10-26): `gpt-oss:20b` passes

Three `poll_override_90020bd` runs, excluded from scoring:

| record | first attempt | wall | prompt / output tokens | thinking chars |
|---|---|---|---|---|
| `20261027_042742_3f1d2e` | accepted | 77 s | 2,722 / 1,576 | 5,729 |
| `20261027_042859_8ccaa6` | accepted | 31 s | 2,722 / 1,222 | 4,374 |
| `20261027_042930_6f1a1a` | accepted | 39 s | 2,722 / 1,571 | 6,248 |

0 of 3 were unusable, median 39 s (limit 150 s), with no retries, as
predicted. The runner prints each record's stored blocker count, and
those lines were seen: 1, 0, 1. The blocker texts were not read.

### Stage 1 results (scored 2026-10-27): not shipped

Records `measurement_engineer_20261027_143609` to `_145900` (gemma)
and `_145927` to `_152227` (`gpt-oss:20b`), 35 each, sampled after the
reviewer arms. Two `gpt-oss:20b` first attempts (`8a757b`, `e6fef5`)
broke the schema and were accepted on a retry, so they are excluded.
Every blocker and hedge-demoted blocker was labeled in
`engineer_labels.json` (samples `b23_gemma` and `b23_gptoss`) before
either arm was scored, along with every concern and question that
states a known bug's defect. One rule covers both arms; the judgment
calls are in the note `b23_twenty_third`.

| | `gemma4:12b` (control) | `gpt-oss:20b` |
|---|---|---|
| runs scored | 35 | 33 |
| stored blockers | 6 | 29 |
| valid share | 83% | 72% |
| false engineer blockers per review | 0.029 | 0.242 |
| wrong rejects (clean runs with a blocker) | 0 of 10 | 0 of 10 |
| hedge-demoted blockers | 0 | 7 |
| mean recall, blockers | 0.091 | 0.436 |
| mean recall, any item | 0.509 | 0.741 |
| first attempts at the cap | 0 | 0 |
| calls failed closed | 0 | 0 |
| median first-attempt wall | 33 s | 30 s |

**Rule.** Condition 1 holds: recall in any item is 0.232 above the
control's. Condition 2 fails: 0.242 false blockers per review against
a bar of 0.10, though no clean run was wrongly rejected. Condition 3
holds. The confirmation sample was not run.

**The false blockers** (8). Four are `other-fp`, all on
`connect_start_4a86231`, and each is false in the post-state. They claim
that:
- the async completion skips `applyConnectedState`, or ignores the
  error;
- `connectCoreOnly` never registers the frame callback;
- the session is never started.

Only the last is contradicted inside the diff, which shows
`qttune_session_start` in `connectCoreOnly`. The other three assert the
absence of code the model was not shown: the hunks end before the
completion applies the state and logs the error, and they never show the
registration.

Two are `invariant-elsewhere`: on `poll_override_90020bd`, `chans[0]`
called the wrong channel. Two are `deletion`: on
`decode_length_b47687c`, functions the diff removes from the header
were called "declared but not defined". The bar fails even if the two
invariant-elsewhere blockers are counted valid (0.182 per review).

| prediction | outcome |
|---|---|
| gemma: no engineer blockers; recall in any item 0.2–0.4 | missed: 6 blockers in 5 runs (backoff 1, decode length 5; 1 false); recall in any item 0.509 |
| `gpt-oss:20b` Stage 0: passes | held |
| `gpt-oss:20b` blockers in at least 20% of runs | held: 17 of 33 (52%) |
| `gpt-oss:20b` recall in any item at least 0.10 above gemma's | held: +0.232 |
| `gpt-oss:20b` false blockers above 0.10 per review | held: 0.242 |
| ships | held: no |

gemma's archived replies had no blockers because they were all on the
bridge fixture. On the corpus it blocks on the two defects visible in a
single post-change line, the backoff condition and the hardcoded decode
length.

**An observation, no rule.** In the engineer role, `gpt-oss:20b`
stored blockers with mean recall 0.436 at 0.242 false positives per
review. The reviewer control in the twenty-second has 0.423 and 0.382.
gpt-oss gets there without an evidence check, since only the hedge check
filters engineer blockers. This compares different roles, prompts and
judges, so it is not a measurement of `gpt-oss:20b` as the reviewer.
It does make it a reviewer candidate for a registered arm, with the
reviewer prompt and the evidence check.

`MODELS["auto_engineer"]` stays `gemma4:12b`.
