# Multi-Agent Review Tribunal

## TL;DR

A hand-rolled orchestration system for code review that uses adversarial
agents, deterministic guardrails, rule-based adjudication, and empirical
eval harnesses to produce verified merge decisions. Built to demonstrate
what's possible beyond LangChain/AutoGen abstractions — including
publishing its own measured failure rates and fixing them.

**Artifacts produced:** [Decision records](coach_artifacts/) *(incl. a real
300-line refactor debate, re-run after remediation, then N=3 after context
retrieval)*,
[Eval logs](probe_logs/),
[Measured precision data](docs/decisions/0002-adjudication-and-fp-remediation.md),
[Input fixtures](docs/fixtures/)

## Prerequisites

- Python 3.11+
- Ollama (v0.40.0+) with local models pulled
- Git Bash or equivalent shell (Windows) / zsh/bash (Linux/macOS)

## Code Layout

| Module | Purpose |
|---|---|
| `orchestrator.py` | CLI entrypoint (argument parsing and dispatch only) |
| `config.py` | Models, runtime knobs, prompt composition |
| `agent_client.py` | Ollama client — the only module that touches the network; retries invalid or schema-violating replies, then fails closed |
| `adjudication.py` | Pure logic: schema validation, verdict derivation, evidence-quote check, hedge demotion guardrail |
| `debate.py` | Debate loop, transcript templates, repo-context retrieval, judging, decision-record persistence; the round-1 reviewer and round-2 pair measurement modes |
| `golden_tests.py` | Golden suite: LLM fixtures + deterministic guardrail units |
| `reviewer_prompt.py` | Agent system prompts (versioned, single source of truth) |
| `file_metadata.py` | File-path → layer mapping (core / bridge / app) |
| `diff_reader.py` | The one unified-diff reader, shared by the evidence check, retrieval and layer mapping |
| `eval_harness/` | FP-rate probe, model bake-off, round-1 measurement runner and scorer |
| `repo_context.py` | Offline indexer: typedefs, constants, layer map, queued-connection call sites → `repo_context.json`; builds retrieved context packs |
| `tests/` | Deterministic regression tests (fake Ollama, no model needed) |

Dependency direction is acyclic: prompts, layer maps and the diff
reader are leaves → config composes the prompts → agent_client and
adjudication are independent layers
(callers hand adjudication's validators to the client as callbacks) →
debate, golden_tests and repo_context sit on top → orchestrator is just
the handle. `adjudication.py` imports nothing with side effects, and
`tests/` fakes Ollama at the HTTP layer, so the whole regression suite
runs in CI without any model serving.

## Running Locally

Install dependencies and verify Ollama is up:

    pip install -r requirements.txt
    curl http://localhost:11434/api/version

Run the deterministic regression tests (no Ollama needed; CI-safe):

    python -m unittest discover -s tests -v

Run the golden test suite (3 live-model fixtures + 7 deterministic
guardrail regression tests):

    python orchestrator.py --golden

Run the false-positive probe against a clean fixture (`--fixture` is required):

    python -m eval_harness.probe --model laguna-xs-2.1 --fixture ../qttune/core/include/qttune/core.h

Build the repo context pack (`--no-llm` skips the LLM purpose summaries):

    python orchestrator.py --index ../qttune --no-llm

Run a production debate on a real diff (uses the committed context pack
for retrieval when present):

    python orchestrator.py --proposal "Describe the change" --diff path/to/change.diff

Review a header-only C ABI artifact (uses the header-scoped prompt):

    python orchestrator.py --proposal "Describe the header" --context path/to/header.h --header

Each debate prints a summary and writes a decision record to
`coach_artifacts/` relative to the current directory. Run ad-hoc debates
from a scratch directory if you don't intend to commit the record.

## What This Actually Does

This isn't a demo — it was built to review
[QtTune](https://github.com/erickramer42/qttune), my cross-platform ECU
tuning application. The tribunal processes code diffs or full artifacts,
runs debates of up to 3 rounds between a code reviewer and a domain
expert agent, passes their outputs through deterministic guardrails, and
produces structured decision records for downstream consumption.

Pipeline per round:

```
TRANSCRIPT (proposal + fenced diff/context + layer note + prior-round feedback)
    → AGENTS CRITIQUE (same transcript, neither sees the other's reply)
    → SCHEMA VALIDATION (retry, then fail closed as AGENT_FAILURE)
    → EVIDENCE CHECK (blockers not quoting post-change code → questions)
    → HEDGE DEMOTION (speculative blockers → questions)
    → RULE-BASED JUDGE (derived verdicts, fail-closed)
    → CONVERGED, or feedback fed back for another round
```


Possible outcomes: `APPROVED_FOR_MERGE`, `APPROVED_WITH_OPEN_QUESTIONS`,
`MAX_ROUNDS_EXCEEDED - MANUAL_REVIEW_REQUIRED`, and
`AGENT_FAILURE - MANUAL_REVIEW_REQUIRED`. A round converges once
neither agent has a blocker: `APPROVED_FOR_MERGE` when both replies are
empty, `APPROVED_WITH_OPEN_QUESTIONS` when questions or concerns remain
(since judge `j2-no-blockers`, 2026-10-22). Until then convergence also
required the engineer to raise zero concerns, so every recorded debate
ended at max rounds.

An offline indexer (`--index`) builds a repo context pack of type
definitions, constants, file purposes and queued-connection call sites
for the target codebase. At debate time, retrieval pulls the entries
tied to the diff into the transcript under a character budget
(non-fatal and recorded via `pack_report` on failure), so reviewers
assert less about code they cannot see. Injected in v5-context-pack and
measured N=3 — see ADR-0002.

### Key Design Decisions

1. **Verdict derivation from content, not model labels** — Model
   self-reported verdicts exhibit run-to-run jitter. Merge decisions
   derive deterministically from blockers/questions counts (see
   `derive_verdict()` in adjudication.py). A reply whose arrays are
   missing or malformed is never read as "no problems found".

2. **Hedge-language demotion** — A blocker must be a demonstrable
   violation, stated with a line citation. Blockers phrased as speculation
   ("may", "might", "could", "needs verification") are deterministically
   demoted to the questions channel (`demote_hedged_blockers()`).
   Regression-tested against real production blocker texts — see
   `run_hedge_unit_tests()`. A reviewer blocker is read without its
   quoted code (judge j6), so a "may" in a quoted comment doesn't
   count. If the reviewer hedges, it is not a blocker: one hedge word
   demotes the whole claim, even one that cites a line or quotes
   verified code. That is deliberate. The context-pack measurement
   caught it demoting a hedged TRUE claim, and the claim stayed visible
   as an open question, not a blocker.

3. **Layer-aware review context** — File paths are mapped to QtTune's
   layer structure (core / bridge / app) and injected into the transcript
   (file_metadata.py), so core-module rules (no Qt headers, C ABI purity)
   don't fire on bridge-layer code where Qt is legitimate.

4. **Prompt scoping by artifact type** — Header-only C ABI stubs vs.
   implementation code require different expectation levels (see
   `HEADER_SCOPE_CLAUSE` in reviewer_prompt.py).

5. **Multi-run eval probes over single-run benchmarks** — Variance is
   information. See probe_logs/ for 5-run aggregates, and ADR-0002's
   N=3 context-pack measurement for why single runs can't be trusted
   with this model class.

6. **Unusable replies fail closed** — Invalid JSON, schema violations
   (wrong, missing or nested keys), timeouts and server errors are
   retried with a corrective message, then end the debate as
   `AGENT_FAILURE - MANUAL_REVIEW_REQUIRED` with the reason recorded.
   They block merges rather than slipping through (see agent_client.py
   and `normalize_agent_output()` in adjudication.py).

7. **Prompts as versioned single source of truth** — PROMPT_VERSION
   stamps appear in every decision record, enabling correlation between
   eval results and production runs. Records also carry a
   `prompt_fingerprint`, a hash of the exact templates used, which
   catches drift that a hand-bumped version string would miss. A
   `judge_version` stamp does the same for the convergence rule, which
   changes verdicts without changing any prompt.

8. **Self-describing decision records** — Each record holds the original
   proposal, SHA-256 hashes of the diff and context, the detected layer,
   sampling settings, per-round evidence- and hedge-demotion counts, per-attempt token
   telemetry (`prompt_eval_count`, `eval_count`, `done_reason`, wall
   time), the exact retrieved pack with its hash and index version
   (`repo_context_pack`) and any agent failure reasons, so a record can
   be matched to its fixture and re-run.

9. **Repo-context retrieval** — Indexed context (file purposes, type
   definitions, constants, queued-connection call sites) keyed to the
   diff is injected into the transcript under a char budget. The diff
   stays authoritative: the pack is labelled a snapshot, and indexed
   entries the diff removes are omitted and named rather than asserted
   (v6, after a reviewer cited a line that existed only in the stale
   index). The
   pack's template and format version participate in the prompt
   fingerprint; the pack text itself is recorded separately, because it
   depends on the reviewed diff. Rationale:
   no output filter can fix a model confidently asserting facts it
   cannot see — only showing it the facts can.

10. **Blockers must quote their evidence** — Each reviewer blocker is
    `{claim, file, quote}`. The quote must be code as it reads after
    the change, and the prompt says a wrong blocker costs more than a
    question. `demote_unverified_blockers()` moves any blocker whose
    quote is not in that file's post-change lines to the questions
    channel (judge j4, measured; j5 also reads diffs that have no hunk
    headers, and j6's hedge check skips the quote; neither changes a
    recorded result). This makes guessing
    expensive mechanically instead of by asking for confidence. Arm H
    found that the reviewer did not hedge more when the hedging ban was
    lifted: its wrong blockers are confident misreadings, and only a
    check against the code catches those. Known limit: a quote proves
    the code exists, not that it supports the claim.

11. **Reviewed code is fenced as data** — The diff and context sit
    between BEGIN DATA and END DATA lines whose mark is hashed from that
    input, so a comment in a reviewed diff cannot close the fence and
    pose as instructions. A truncated context says so. Feedback still
    goes into the proposal: a separate critiques section was measured
    against it in paired round-2 runs (ADR-0002, eleventh measurement).
    It matched on precision but dropped a real removal-caused blocker
    and ran away more often, so it was not shipped.

## Measured Production Precision (the honest part)

On synthetic fixtures, the reviewer scored 100% (3/3 golden, 0/5
false-positive rate across probe runs). On its first real workload —
a 300-line bridge refactor — blocker precision was **1/12 (~8%)**.
The gap was root-caused into classes, remediated, and re-measured
twice — with predictions recorded before each run:

| Failure class | Baseline | After v1 | After v5 context pack (N=3) | Status |
|---|---|---|---|---|
| Layer-rule misapplication (core rules on bridge code) | 7 | 0 | 0 | **Fixed** — layer metadata injection |
| Speculative phrasing filed as blockers | 3 | 0 | 0 | **Fixed** — taxonomy discipline; hedge guardrail in reserve |
| Confident-but-wrong assertions (missing context) | 0 | 4 | **0 in 3/3 runs** | **Fixed** — context retrieval; residual concern moved to questions |
| Deletion-hallucination (fabricated surviving remnants) | 0 | 0 | 8 | **Mostly fixed (2026-10-22)** — 0.5/run at v6 → 0.1/run with evidence-quoted blockers (N=10 each) |
| True positives | 1 | 1 | 2 | See below |

Round-1 precision: 1/12 (~8%) → 1/6 (~17%) → **2/10 (20%)**, N=3.

The two context-pack true positives are the strongest result in the
project's history — and they were only recognizable as true positives
after forensic re-adjudication. The fixture diff turns out to be the
reverse patch of a real merged QtTune commit, so its post-state is a
formerly-shipped codebase state; both TPs (a cumulative-gate frame
freeze past 10k frames, and a worker-thread read of GUI-owned
`m_currentFrameCount`) are bugs that actually shipped and were later
fixed in QtTune's real history. The reviewer detected both from a
diff alone. That same forensics invalidated the refutation behind
the v1 "confident-but-wrong" FP labels — those runs are flagged for
re-triage in ADR-0002 rather than silently re-scored. Publishing the
corrections is the point of this section.

The offsetting cost is honest too: total FP volume did not fall. It
migrated to a new class — the reviewer confidently fabricates
surviving references to code the diff removes together (6/0/1 by
run: extreme variance), one run died of num_ctx exhaustion in round 2,
and the hedge guardrail demoted a hedged *true* claim. All recorded,
all queued for per-class remediation.

**Update (2026-10-22, ADR-0002, sixth to tenth measurements; 10
round-1 samples per arm).**
- The deletion class persisted at v6 (0.5 per run) even with the
  context pack fixed, so it does not need the pack.
- Lifting the hedging ban did not make the reviewer hedge more.
- Requiring a quote from either side of the diff only moved the class
  onto removed lines.
- **Requiring post-change quotes worked.** Stored round-1 blockers
  became 94% valid (17 of 18, against 11 of 26 at v6), with deletion
  FPs at 0.1 per run and 2 valid blockers lost to the check.
- This is one fixture. The stable corpus (STATUS #7) is the next test
  of whether it holds.
- **Fencing the input (eleventh measurement) kept round 1's precision**
  at 80% of stored blockers, with the race found in all 10 runs and 0.1
  deletion FPs per run. It also showed 4 other FPs, against G3's 0, so
  it is worth watching.

Evidence: baseline `coach_artifacts/decision_debate_20261007_203917.json`,
re-measurement `coach_artifacts/decision_debate_20261009_014257.json`,
live-loop control `decision_debate_20261013_170208_71915a.json`,
context-pack pilot `decision_debate_20261013_201540_ff958c.json` and
three scored runs (`20261013_203802`, `20261013_204845`,
`20261013_210548`), input `docs/fixtures/qttune_bridge_refactor.diff`,
full analysis in
[ADR-0002](docs/decisions/0002-adjudication-and-fp-remediation.md).

Fixture-pass / production-fail is a known trap in eval harnesses. This
repo measures both — repeatedly, with predictions recorded before each
run, and with corrections published when measurement triage turns out
to be wrong.

## Running the Eval Harness

Command examples:

- Probe false-positive rate on clean headers:
  `python -m eval_harness.probe --model laguna-xs-2.1 --fixture ../qttune/core/include/qttune/core.h`
  Classifies the model CLEAN / BORDERLINE / SYSTEMATIC, or NO DATA when
  every run times out or fails to parse; failed runs count against it.
- Bake-off, detection vs. false positives:
  `python -m eval_harness.bakeoff laguna-xs-2.1 gemma4:12b`
  A parse failure or timeout on a bug case counts as a miss.
- Diff-based review example (the archived debates):
  `python orchestrator.py --proposal "..." --diff docs/fixtures/qttune_bridge_refactor.diff`
- Round-1 reviewer samples, the arm that measurements score:
  `python -m eval_harness.round1 run --proposal "..." --diff docs/fixtures/qttune_bridge_refactor.diff --runs 6`
  Each sample is the reviewer call a debate's first round makes, same
  prompt and settings, without the rest of the debate. Records go to
  `coach_artifacts/measurement_*.json`.
- Score round-1 blockers from measurement or debate records:
  `python -m eval_harness.round1 score --diff docs/fixtures/qttune_bridge_refactor.diff --symbols SignalListModel,MaxInFlightFrames,m_inFlightFrames --repo ../qttune --rev 8ffbf19 "coach_artifacts/*.json"`
  First attempts on that exact diff only. It counts M1 and lists M2
  candidates for confirming by hand (ADR-0002, fifth measurement).

## What Makes This Different From Tutorial Projects

| Typical "Multi-Agent" Repo | This Repo |
|---|---|
| Demo prompt → demo output | Eval harness with failure modes, remediation logs |
| Single run, cherry-picked | N-run aggregates with variance reporting |
| Prompts hardcoded, no version | PROMPT_VERSION stamps every decision record |
| Only clean results shown | 8% precision published, root-caused, remediated, re-measured at 17%, then 20% (N=3) — corrections included |
| No evaluation methodology | Golden tests, probe logs, ADRs documenting decisions, model-free regression suite |
| "Works on my toy example" | Runs on actual codebase (QtTune); caught two real previously-shipped bugs from a diff alone |

## Transferable Patterns

These patterns work on ANY codebase:

- Derived verdicts → any merge-blocking review system
- Schema validation before judging → a malformed reply must never read as "no findings"
- Hedge demotion → enforce taxonomy discipline on any LLM output
- Layer/role metadata injection → applies wherever file-level rules differ
- Repo-context retrieval → give reviewers indexed facts keyed to the diff, not the whole repo, and never let a stale index overrule the diff
- Artifact-type prompting → headers vs. implementations differ everywhere
- Multi-run probes → stability is a property of the eval harness, not the model
- Measure → remediate per class → re-measure → publish the trend → this loop is the repo's core contribution
- Forensic re-adjudication of eval ground truth → when triage refutations come from the wrong code state, your FP labels are wrong too

## Reproducing the Results

All numbers in docs/decisions/ are reproducible via the eval harness.
The probe_logs/ directory contains timestamped JSON artifacts for each
run. The probe and bake-off scoring were corrected on 2026-10-10 so that
parse failures and timeouts count against a model; ADR-0001's timeout
row predates a working timeout counter (details in STATUS.md). The
context-pack measurement (ADR-0002, fourth measurement) is reproducible
by running the debate command three times against the committed fixture
and index. The regression suite in tests/ runs without any LLM and is
suitable for CI.

## Project Map and Backlog

See [STATUS.md](STATUS.md) for a full file map, current state, known
limitations, conventions and the backlog.

## Links

- QtTune Repository: https://github.com/erickramer42/qttune
- Ollama: https://ollama.com
