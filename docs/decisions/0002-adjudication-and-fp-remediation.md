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

## Sixth Measurement (Pending) — v6 Baseline

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

## Seventh Measurement (Parked) — Survival-Claim Check (backlog #15)

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

## Eighth Measurement (Pending) — Arm H: No Hedging Ban

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

## Ninth Measurement (Pending) — Arm G: Evidence-Quoted Blockers

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

## Tenth Measurement (Pending) — Arm G3: Post-Change Quotes

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

## Eleventh Measurement (Pending) — Transcript Protocol v10 (backlog #11)

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

## Twelfth Measurement (Pending) — Feedback Section v11 (backlog #11)

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

## Thirteenth Measurement (Pending) — Offline Replay of Judge Variants

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

## Fourteenth Measurement (Pending) — Corpus Baseline (backlog #7)

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
