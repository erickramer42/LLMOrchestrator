# Measured Results

How the tribunal performed on real code, what went wrong, and what each
fix changed. The full record, with every prediction written before its
run, is [ADR-0002](decisions/0002-adjudication-and-fp-remediation.md).
Model selection is [ADR-0001](decisions/0001-model-selection.md).

## Synthetic fixtures were not enough

On synthetic fixtures, the reviewer scored 100%: 3 of 3 golden fixtures
passed, and the probe found no false positives in 5 runs on a clean
header. On its first real workload, a 300-line refactor of QtTune's
Qt bridge, **2 of 12 blockers were correct (17%)**.

Fixture-pass, production-fail is a known trap. This repo measures both.

## Fixing it class by class

The false positives were sorted into failure classes, each class was
fixed, and the result was re-measured. The input is the same diff every
time, [docs/fixtures/qttune_bridge_refactor.diff](fixtures/qttune_bridge_refactor.diff).

The early runs were labelled again on 2026-10-23, against the code as
the diff leaves it. The first labels had relied on the current QtTune
tree, and they were wrong in both directions (below).

| Blockers | First run | After v1 | After context pack (N=3) |
|---|---|---|---|
| Counted | 12 (3 rounds) | 6 (3 rounds) | 10 (round 1) |
| **Valid:** the data race | 2 | 4 | 1 |
| **Valid:** the removed backpressure gate | 0 | 0 | 2 |
| Layer-rule misapplication (Qt includes in bridge code) | 3 | 0 | 0 |
| A defect in code the diff removes, read as current | 2 | 1 | 0 |
| Deletion hallucination (claims that removed code survives) | 1 | 0 | 6 |
| Other false positives | 4 | 1 | 1 |
| **Precision** | **2 of 12 (17%)** | **4 of 6 (67%)** | **3 of 10 (30%)** |

- **Layer metadata** in the transcript removed the layer-rule false
  positives. **Taxonomy discipline and the hedge guardrail** keep
  speculation out of blockers.
- **The repo-context pack did not remove a false-positive class.** Its
  target, confident thread-safety claims, turned out to be the real
  race. With the pack, the race was found in 1 of 3 runs. The first
  gate blockers and the deletion hallucinations appeared with it.
- **Deletion hallucinations** fell from 0.5 per run to 0.1 with
  evidence-quoted blockers (10 samples each).
- **Single debates are noisy.** The first two columns are one debate
  each. "4 of 6" is the same race, stated four times.

### Later measurements

The later measurements took 10 round-1 samples each.

| Change | Valid share of stored blockers | Notes |
|---|---|---|
| Diff made authoritative over the context pack | 42% (11 of 26) | Deletion hallucinations persisted at 0.5 per run, so they did not come from the pack. |
| Removing the ban on hedged blockers (not shipped) | 58% (15 of 26) | The reviewer did not hedge more. Its wrong blockers are confident misreadings. |
| Quotes accepted from either side of the diff (not shipped) | 60% | The hallucinations moved to quoting removed lines. |
| **Quotes must be post-change code (shipped)** | **94% (17 of 18)** | 0.1 deletion hallucinations per run; 2 valid blockers lost to the check. |
| **Input fenced as data (shipped)** | **80% (20 of 25)** | The data race was found in 10 of 10 runs; 4 other false positives, against 0 before. A replication gave 94% (17 of 18) and 1 other false positive. |
| Separate critiques section in round 2 (not shipped) | 93% in both arms | It dropped a real blocker and ran away more often. |
| **Critiques section revised: a checked blocker stands (shipped, current)** | 94% in both arms | Round 2 only. Each arm moved the gate blocker to a question once; runaways 2 against 1. |

"Valid" means the blocker was judged correct in a hand review against
the diff's post-state. ADR-0002 lists every blocker with its label.

## Two real bugs, found from a diff alone

The fixture diff is the reverse patch of a real merged QtTune commit, so
the code it leaves is a state of QtTune that actually shipped. That code
has two known bugs, both later fixed in QtTune's history:
- a worker-thread read of the GUI-owned `m_currentFrameCount`, a data
  race;
- a backpressure gate on the cumulative frame count. It does not bound
  the queue, and it freezes frame processing past 10,000 frames.

The reviewer found both from the diff alone. It flagged the race from
the first run on, but the early triage labelled those blockers false
positives, from the current QtTune tree. Forensics on the fixture
flagged them on 2026-10-13, and the 2026-10-23 re-triage corrected them.
The gate was first a blocker with the context pack, and a later sample
stated the freeze itself.

The re-triage also corrected the other way. The first run's only
"true positive", a hardcoded 8-byte decode buffer, is a real QtTune bug
in code that this diff removes. As a blocker on this diff, it is
wrong.

No exhaustive triage of the fixture has been done, so these two are the
known bugs, not necessarily all of them. ADR-0002, "Re-Triage of the
Early Runs", has every blocker's old and new label.

## What it cost

- **False-positive volume did not fall at first. It moved.** With the
  context pack, the reviewer started inventing surviving references to
  code the diff removes (6 in one run of three, none in the others).
  Evidence-quoted blockers later removed most of it.
- **One run ran out of context** in round 2. Telemetry later showed that
  thinking output, not the prompt, fills the window. Output is now
  capped, and oversized input is refused.
- **The hedge guardrail demoted a hedged true claim.** This is by
  design: a hedged claim is a question, and it stays visible in the
  verdict.
- **This is one fixture.** A corpus of triaged real diffs is the next
  test of whether the precision holds (STATUS backlog #7).

## Evidence

The records are committed alongside their inputs.
- **Decision records:**
  - baseline: `coach_artifacts/decision_debate_20261007_203917.json`;
  - re-measurement: `coach_artifacts/decision_debate_20261009_014257.json`;
  - live-loop control: `decision_debate_20261013_170208_71915a.json`;
  - context-pack pilot: `decision_debate_20261013_201540_ff958c.json`;
  - three scored context-pack runs: `20261013_203802`,
    `20261013_204845` and `20261013_210548`.
- **Measurement records:** `coach_artifacts/measurement_round1_*.json`
  and `measurement_round2_*.json`, 10 samples per arm.
- **Probe logs:** [probe_logs/](../probe_logs/).
- **Input fixture:** [docs/fixtures/](fixtures/).

## Reproducing the results

Every number in `docs/decisions/` comes from committed records and can
be re-run with the eval harness; [usage.md](usage.md) has the commands.
- **The context-pack measurement** (ADR-0002, fourth measurement): run
  the debate command three times against the committed fixture and
  index.
- **The fifth to eleventh measurements:** `eval_harness.round1` and
  `eval_harness.round2` against the same fixture. Each record names its
  prompt version, judge version and prompt fingerprint, so a rerun can
  be matched to the original.
- **Probe and bake-off:** their scoring was corrected on 2026-10-10, so
  that parse failures and timeouts count against a model. ADR-0001's
  timeout row predates a working timeout counter.

Live runs are nondeterministic. The regression suite in `tests/` needs
no model and is the pass/fail signal.
