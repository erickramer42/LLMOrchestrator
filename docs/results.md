# Results

What the tribunal achieved on real code, what each change did, and what
did not work. Every number here comes from committed records and hand
labels; the full log, with each prediction written before its run, is
[ADR-0002](decisions/0002-adjudication-and-fp-remediation.md). Model
selection is [ADR-0001](decisions/0001-model-selection.md).

**In short:**
- On its first real diff, 2 of 12 blockers were correct (17%). After
  fixes made one failure class at a time, 94% of the reviewer's stored
  blockers are valid on that diff.
- From that diff alone, the reviewer found two real bugs that had
  shipped in QtTune and were fixed later.
- On a corpus of seven other real diffs, precision is lower: 64% of
  stored blockers are valid, with a mean recall of 0.41 per known bug.
  That gap is the current frontier, and six measured attempts to close
  it are published below, failures included.

## How the measurements work

- **One call, many samples.** A measurement samples the reviewer's
  round-1 reply 10 to 20 times per input. Round 1 is the only call
  free of the other agent's influence, and single debates proved too
  noisy to compare.
- **Hand labels against the right code.** Each blocker is labeled valid
  or false against the code as the diff leaves it, by failure class.
  Labels are written before any score is computed.
- **Pre-registration.** Each change's prediction and ship rule go into
  ADR-0002 before the first sample. Changes made after seeing data are
  dated amendments, and a missed prediction stays in the record.
- **Cheap checks first.** Judge changes are first replayed offline over
  archived replies (no model). New levers get a no-model ceiling check
  ("could this reach the bar at all?") and a three-call pilot with a
  registered exit before any batch.
- **Controls when the baseline is in doubt.** The twenty-first
  measurement sampled the shipped prompt alongside the candidate.

## The bridge fixture: from 17% to 94%

The first real workload was a 300-line refactor of QtTune's Qt bridge,
[qttune_bridge_refactor.diff](fixtures/qttune_bridge_refactor.diff). On
synthetic fixtures the reviewer had scored 100%; here 2 of 12 blockers
were correct. The false positives were sorted into classes, each class
was fixed, and the result was re-measured on the same diff.

| Blockers | First run | After v1 guardrails | With the context pack (N=3) |
|---|---|---|---|
| Counted | 12 (3 rounds) | 6 (3 rounds) | 10 (round 1) |
| **Valid:** the data race | 2 | 4 | 1 |
| **Valid:** the removed backpressure gate | 0 | 0 | 2 |
| Layer rules misapplied (Qt includes in bridge code) | 3 | 0 | 0 |
| A defect in code the diff removes, read as current | 2 | 1 | 0 |
| Claims that removed code survives | 1 | 0 | 6 |
| Other false positives | 4 | 1 | 1 |
| **Precision** | **2 of 12 (17%)** | **4 of 6 (67%)** | **3 of 10 (30%)** |

Then 10 round-1 samples per change:

| Change | Valid share of stored blockers | Notes |
|---|---|---|
| Diff made authoritative over the context pack | 42% (11 of 26) | Claims of surviving removed code held at 0.5 per run, so they did not come from the pack. |
| Removing the ban on hedged blockers (not shipped) | 58% (15 of 26) | The reviewer did not hedge more; its wrong blockers are confident misreadings. |
| Quotes accepted from either side of the diff (not shipped) | 60% | The false claims moved to quoting removed lines. |
| **Blockers must quote post-change code (shipped)** | **94% (17 of 18)** | Claims of surviving removed code fell to 0.1 per run; 2 valid blockers lost to the check. |
| **Reviewed code fenced as data (shipped)** | **80% (20 of 25)** | The data race in 10 of 10 runs. A replication gave 94% (17 of 18). |
| **Previous round's critiques in their own section (shipped)** | 94% in both arms | Round 2, paired against the old format; no metric worse. |
| **Claim–quote linkage, judge j8 (shipped)** | 94% (control, 19 runs) | 0.11 false positives per review; the race in 53% of runs, the gate in 42%. |

"Valid" means correct in a hand review against the diff's post-state.
ADR-0002 lists every blocker with its label.

## Two real bugs, found from a diff alone

The fixture is the reverse patch of a merged QtTune commit, so the code
it leaves is a state of QtTune that actually shipped. That code has two
bugs, both fixed later in QtTune's history:
- a worker-thread read of the GUI-owned `m_currentFrameCount`, a data
  race;
- a backpressure check on the cumulative frame count, which does not
  bound the queue and freezes frame processing past 10,000 frames.

The reviewer found both from the diff alone. The early triage had
labeled the race blockers false positives, because it checked them
against the current QtTune tree instead of the diff's post-state. A
re-triage on 2026-10-23 corrected that in both directions: the race
blockers became true positives, and the first run's only "true
positive", a hardcoded 8-byte decode, turned out to be in code the diff
removes. The lesson carried into every later measurement: label against
the code the diff leaves.

## The corpus: does it generalize?

A corpus of seven real QtTune diffs tests whether the fixes transfer.
Five reverse a bug-fix commit, so each reintroduces known bugs (eleven
in all); two are clean forward changes, for a false-positive rate. Each
diff gets an index of its own base commit.

| Measurement | Runs | Valid share | False positives per review | Mean recall per bug |
|---|---|---|---|---|
| Baseline (fourteenth) | 33 | 57% | 0.55 | 0.46 |
| With claim–quote linkage, j8 (both samples) | 66 | 64% | 0.41 | 0.41 |

What the corpus showed:
- **The quote rule costs recall where bugs are removals.** 14 of the 17
  items the evidence check demoted in the baseline were valid: the bugs
  are deleted safety checks, and the reviewer quotes the deleted lines,
  which a blocker may not do.
- **A new false-positive class:** a removed check whose invariant
  another function enforces. It accounts for about half the stored
  false positives, all on one diff.
- **Voting across samples does not transfer.** It cut bridge false
  positives, but on the corpus the false claims recur across samples,
  and voting raised false positives from 0.55 to 0.98 per review
  (offline replay, fifteenth measurement).
- **Claim–quote linkage does.** A blocker whose claim names code that
  its quote's hunk does not contain becomes a question. On a fresh
  sample, labeled before replay, it cut false positives from 0.39 to
  0.30 per review with recall unchanged, and shipped as judge j8.

## Levers that did not ship

Each was registered with a prediction and a ship rule, and each failed
its rule. They are kept because the reasons are informative.

| Measurement | Idea | Result | Why |
|---|---|---|---|
| Seventeenth | A second reviewer call that offers back blockers demoted for their quotes, asking only for a new quote | Recall +0.009 against a +0.10 bar | 19 of 33 calls ran to the output cap and 6 answered as a fresh review: the request kept the reviewer's role. |
| Eighteenth | A dedicated repair prompt (two pilots) | Closed at the pilot | A no-model ceiling showed the bar reachable only if the model declined almost every false claim; in the pilot it declined its valid ones too. |
| Nineteenth | A round-1 prompt rule: quote the line a removal leaves unprotected | Recall +0.05 against +0.10 | Most valid claims still quoted removed lines; where they did not, the quoted code sat in another hunk, which linkage refuses. |
| Nineteenth, amendment | Linkage across hunks for such claims | Closed without a run | Replaying with no linkage at all bounds any variant at +0.02 recall. |
| Twentieth | Show the model the unchanged function that enforces a removed check | Target false positives rose, 1.33 → 1.67 per review | Every request carried the refuting code and no claim used it; the new section also tripled the bridge's false positives, which a control run confirmed. |
| Twenty-first | Give each file of a multi-file diff its own layer rules, not only the first file's | Bridge false positives 0.11 → 0.33 per review, against a bar of 0.21 | The target class did not move (1.11 → 1.05 per run). On the bridge, naming the QML file drew claims toward the removed UI feature, and some quoted lines the evidence check accepts. |
| Twenty-second | Another local reviewer model of the same size class | `qwen3-coder:30b`: mean recall 0.09 against laguna's 0.42 | It stored blockers in 5 of 35 runs, all for the one bug visible on a single post-change line. `nemotron-3.5-lightning:30b` ran every first attempt to the output cap and was dropped before the corpus. |
| Twenty-third | `gpt-oss:20b` as the engineer instead of `gemma4:12b` | Recall in any item 0.74 against 0.51, but 0.24 false blockers per review against a bar of 0.10 | Of its 8 false blockers, 3 claimed that code the hunks did not show was missing, and 2 read removed declarations as current. An engineer blocker forces a reject and has no evidence check. |
| Twenty-fourth | `gpt-oss:20b` as the reviewer | Mean recall 0.31 against laguna's 0.44; false positives 0.73 times laguna's, against a bar of 0.7 | It stored fewer blockers, and most of the drop was valid ones. The evidence check demoted its claims of missing code, which had stood when it was the engineer. Taking either model's blockers raised recall to 0.56 but false positives to 0.74 per review. |

**What these taught:**
- Facts placed in front of a small model are not facts it uses; the
  invariant-elsewhere claims did not change when the refuting function
  was in the prompt.
- A request that keeps an agent's role gets that role's behavior, not
  the new task.
- What a request names, the model looks at: listing a UI file with UI
  rules turned bridge claims toward the UI change, even though the
  rules were correct.
- A ceiling check without a model is worth running first: twice it
  showed whether a lever could reach its bar before any GPU time.

## What it cost

- **False positives moved before they fell.** With the context pack,
  the reviewer began inventing surviving references to removed code.
  Evidence-quoted blockers later removed most of them.
- **Thinking can run to the output cap.** About 5% of first attempts;
  the retry usually recovers but costs minutes. Output is capped, and
  oversized input is refused before any model call.
- **The hedge guardrail demotes hedged true claims**, by design. They
  stay visible as open questions.
- **Recall on removal-caused bugs** is the price of the quote rule, and
  the levers above did not buy it back.

## Evidence and reproduction

- **Records:** `coach_artifacts/` holds every debate and measurement
  record, each stamped with its prompt version, judge version and
  prompt fingerprint, so a rerun can be matched to the original.
  [file-map.md](file-map.md) and [history.md](history.md) say which
  records belong to which measurement.
- **Labels:** `eval_harness/labels.json` (bridge fixture) and
  `eval_harness/corpus_labels.json` (corpus); tests pin each sample's
  label counts.
- **Inputs:** [docs/fixtures/](fixtures/), with the corpus manifest
  and each fixture's index.
- **Commands:** [usage.md](usage.md). The offline replay re-scores
  archived records with no model.

Live runs are nondeterministic; the regression suite in `tests/` is the
pass/fail signal.
