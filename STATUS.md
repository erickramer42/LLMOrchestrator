# Status

Last updated: 2026-10-26.

What works today, what is being measured, what is known to be weak, and
what comes next. For the system itself see [design.md](docs/design.md);
for the numbers, [results.md](docs/results.md); for where every file
lives, [file-map.md](docs/file-map.md); for how the project got here,
[history.md](docs/history.md).

## At a glance

| | |
|---|---|
| Shipped prompt | `v11.1-critiques-feedback` (debate fingerprint `8e76794ac4946aab`) |
| Judge | `j8-claim-quote-linkage` |
| Context-pack format | `f3-diff-authoritative` |
| Models | reviewer `laguna-xs-2.1`, engineer `gemma4:12b`, on Ollama; `NUM_CTX` 24576, `NUM_PREDICT` 12288 |
| Tests | 213 regression tests, no model needed; CI on Python 3.11 and 3.13 |
| Golden suite | 10/10 live (3 model fixtures, 7 hedge units) |

**Headline numbers (judge j8, round-1 samples, hand-labeled):**
- **Bridge fixture**, v11.1 control of 2026-10-26 (19 runs): 30 of 32
  stored blockers valid (94%), 0.11 false positives per review, the
  data race found in 53% of runs and the backpressure gate in 42%.
- **Corpus of seven real diffs**, v11.1 (66 runs): 64% of stored
  blockers valid, 0.41 false positives per review, mean recall 0.41 per
  known bug.

## In progress

Nothing is being measured. The shipped prompt is v11.1; the next
candidates are in the backlog's suggested order.

## Recently closed

Each was registered with a prediction and a ship rule before it ran,
and each is in ADR-0002 in full.

| Measurement | Lever | Outcome |
|---|---|---|
| 17th, 18th | A repair call that re-quotes blockers the evidence check demoted | Closed: the model declined its own valid claims as readily as its false ones |
| 19th | A round-1 prompt rule for quoting removal-caused defects | Not shipped: recall +0.05 against a +0.10 bar |
| 19th, amendment | Cross-hunk claim–quote linkage | Closed without a run: its ceiling is below the bar |
| 20th | Field definitions and writer functions in the context pack | Not shipped: target false positives rose (1.33 → 1.67 per review), and the bridge's tripled |
| 21st | Per-file layer notes for multi-file diffs (#8) | Not shipped: bridge false positives rose (0.11 → 0.33 per review, against a bar of 0.21); invariant-elsewhere unchanged |
| Runaway diagnostic | Abort a reply whose thinking repeats (#19) | Closed: of 3 runaways with whole thinking, 1 looped and 2 kept reopening their conclusion; no repetition threshold separates them from long accepted replies, and an early retry at a token budget cuts more valid findings than false ones |

## Known limitations

- **Precision drops off the fixture it was tuned on.** 94% of stored
  blockers are valid on the bridge fixture, 64% on the corpus.
- **Removal-caused bugs lose recall to the quote rule.** A blocker must
  quote post-change code, and the reviewer quotes the removed safety
  check instead; over a third of the valid corpus items end as
  questions.
- **One false-positive class resists every lever so far:** a removed
  check whose invariant another function enforces
  (`poll_override_90020bd`). Neither showing the model the enforcing
  function nor giving the core file its own layer rules changed it
  (twentieth and twenty-first measurements).
- **A multi-file diff gets only its first file's layer rules** (#8).
  Sending each file's rules was measured and cost bridge precision.
- **A quote proves the code exists, not that it supports the claim.**
  Claim–quote linkage (j8) catches claims about code the quote's hunk
  does not contain, nothing finer.
- **A deleted test cannot be a blocker:** its lines exist only on the
  removed side, so the objection becomes a question.
- **Hedged true claims are demoted, by design.** A hedged claim is a
  question; it stays visible in the verdict.
- **The reviewer sometimes thinks until the output cap.** About 6% of
  first attempts; the retry usually recovers but costs 3–5 minutes, and
  on 2026-10-26 two bridge samples failed all three attempts (#19).
- **Retried replies are a different mode** (short, little thinking); the
  scorers exclude them.
- **Debates with reviewer blockers rarely converge** before the round
  limit, and round 2 mostly repeats round 1. Measurements therefore
  score round 1 (#18).
- **The bridge fixture's proposal contradicts its diff** (#21). It is
  kept constant so every run compares with every other.
- **Diffs above about 30K characters are refused** at the current
  context window, rather than truncated.
- **Live runs are nondeterministic.** The regression suite is the
  pass/fail signal.

## Backlog

Numbers are stable (code comments and the ADRs cite them) and never
reused. Done items are removed; their history is in
[history.md](docs/history.md).

**Suggested order:** a local-model bake-off on the corpus (with #13) →
#14 structured outputs → #18 early reject → the rest. The call-site
caveat (code review finding 9) rides on the next pack change rather
than being measured alone.

- **#2 Judge granularity.** Split a finding's severity from whether it
  is resolved. The minimal form shipped as judge j2: a round with no
  blockers converges with its open questions.
- **#6 Escalated debates.** On `MAX_ROUNDS_EXCEEDED`, re-submit the
  unresolved questions as a fresh debate. Depends on #2.
- **#7 Corpus.** Built and baselined (fourteenth to sixteenth
  measurements). Open: more fixtures, especially one where a check is
  enforced in an unchanged function, to test the invariant-elsewhere
  class beyond one diff.
- **#8 Multi-file layer notes.** Measured as v16 (twenty-first): the
  per-file notes drew bridge claims toward the removed UI feature
  (false positives 0.11 → 0.33 per review) and left invariant-elsewhere
  unchanged. Open, with no successor registered.
- **#10 Codebase abstraction.** Move the QtTune-specific parts (layer
  rules, the engineer's domain, fixtures) behind configuration.
- **#13 Probe rerun.** Rerun the probe on the committed `core.h` with
  the fixed scoring; folded into the corpus bake-off.
- **#14 Structured outputs.** Pass the JSON schema as Ollama's `format`.
  This changes how replies are sampled, so it needs a prediction and a
  measurement.
- **#18 Early reject.** End a debate as `CONVERGED_REJECT - BLOCKED`
  once a rejection is settled. Option A: both derived verdicts are
  reject (never fires in round 1, where the engineer has had no
  blockers). Option B: a reviewer blocker and an engineer concern share
  an identifier and a failure-class term. Use round-1 agreement only:
  from round 2 the agents read each other and echo.
- **#19 Runaway cost.** About 6% of reviewer first attempts think to
  the 12,288-token cap (a median 266 s, against 83 s for an accepted
  reply); a retry usually recovers in seconds, but twice on 2026-10-26
  a bridge sample failed all three attempts. Aborting on repetition is
  closed (ADR-0002, "Runaway Diagnostic"): most runaways reopen their
  conclusion on a new question rather than repeat, and long accepted
  replies repeat as much. A lower cap is no abort either, since 10.7% of
  accepted replies run past 8,192 tokens. An early retry on a token
  budget was checked offline and is not worth it: attempts at the cap
  are 14% of reviewer time, and every budget that saves real time cuts
  more valid findings than false ones (ADR-0002, the diagnostic's
  amendment). Open: only the call whose retries run away too (2 of 398
  round-1 calls).
- **#20 Engineer prompt conflict.** Both engineer runaways on record
  alternated between "argue for shipping" and "a violation is a
  blocker". Say what the engineer does with a correctness violation.
- **#21 Bridge proposal mismatch.** The proposal describes adding the
  LiveView page; the diff removes it. A matching proposal would start a
  new baseline.

## Conventions

1. **Verdicts are derived, never self-reported.** The judge reads the
   blocker, question and concern arrays. A change to the judge or the
   convergence rule bumps `JUDGE_VERSION`.
2. **Fail closed.** Parse failures, schema violations, timeouts, empty
   or oversized input end in manual review, never in approval.
3. **Blockers must be demonstrable.** A hedged blocker is a question,
   even with a verified quote. Changes to `HEDGE_PATTERNS` must keep the
   7 hedge units passing.
4. **Prompts are versioned.** Any change to what the agents see bumps
   `PROMPT_VERSION`; transcript templates, layer notes and the pack
   format count, and the pack format also bumps `PACK_FORMAT_VERSION`.
5. **Evidence pairs.** A committed record needs its input fixture
   committed in `docs/fixtures/`.
6. **Predict, then measure.** Each measurement's prediction and ship
   rule go into ADR-0002 before any sample; labels are written before
   scoring; changes after seeing data are dated amendments.
7. **Fix per failure class, re-measure, publish misses with wins.**
8. **Module boundaries.** Only `agent_client.py` (and the probe's
   `raw_call.py`) touches the network; `adjudication.py` stays pure; a
   debate never loads the indexer.
