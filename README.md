# Multi-Agent Review Tribunal

## TL;DR

A hand-rolled orchestration system for code review that uses adversarial
agents, deterministic guardrails, rule-based adjudication, and empirical
eval harnesses to produce verified merge decisions. Built to demonstrate
what's possible beyond LangChain/AutoGen abstractions — including
publishing its own measured failure rates and fixing them.

**Artifacts produced:** [Decision records](coach_artifacts/) *(incl. a real
300-line refactor debate, re-run after remediation)*,
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
| `adjudication.py` | Pure logic: schema validation, verdict derivation, hedge demotion guardrail |
| `debate.py` | Debate loop, transcript templates, judging, decision-record persistence |
| `golden_tests.py` | Golden suite: LLM fixtures + deterministic guardrail units |
| `reviewer_prompt.py` | Agent system prompts (versioned, single source of truth) |
| `file_metadata.py` | File-path → layer mapping (core / bridge / app) |
| `eval_harness/` | FP-rate probe + model bake-off |
| `repo_context.py` | Offline indexer: typedefs, constants, layer map → `repo_context.json` |
| `tests/` | Deterministic regression tests (fake Ollama, no model needed) |

Dependency direction is acyclic: prompts/layer maps are leaves → config
composes them → agent_client and adjudication are independent layers
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

Run a production debate on a real diff:

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
TRANSCRIPT (proposal + diff/context + layer note + prior-round feedback)
    → AGENTS CRITIQUE (same transcript, neither sees the other's reply)
    → SCHEMA VALIDATION (retry, then fail closed as AGENT_FAILURE)
    → HEDGE DEMOTION (speculative blockers → questions)
    → RULE-BASED JUDGE (derived verdicts, fail-closed)
    → CONVERGED, or feedback fed back for another round
```

Possible outcomes: `APPROVED_FOR_MERGE`, `APPROVED_WITH_OPEN_QUESTIONS`,
`MAX_ROUNDS_EXCEEDED - MANUAL_REVIEW_REQUIRED`, and
`AGENT_FAILURE - MANUAL_REVIEW_REQUIRED`. In practice every recorded
debate so far has ended at max rounds: converging requires the domain
agent to raise zero concerns, which it rarely does. Reworking that rule
is on the backlog (see STATUS.md).

An offline indexer (`--index`) builds a repo context pack of type
definitions, constants and a layer map for the target codebase. It is
built and committed, but not yet injected into debates; that is the
next remediation for the dominant false-positive class below.

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
   `run_hedge_unit_tests()`. Known tradeoff: one hedge word demotes the
   whole blocker, even a confident one that cites a line.

3. **Layer-aware review context** — File paths are mapped to QtTune's
   layer structure (core / bridge / app) and injected into the transcript
   (file_metadata.py), so core-module rules (no Qt headers, C ABI purity)
   don't fire on bridge-layer code where Qt is legitimate.

4. **Prompt scoping by artifact type** — Header-only C ABI stubs vs.
   implementation code require different expectation levels (see
   `HEADER_SCOPE_CLAUSE` in reviewer_prompt.py).

5. **Multi-run eval probes over single-run benchmarks** — Variance is
   information. See probe_logs/ for 5-run aggregates.

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
   catches drift that a hand-bumped version string would miss.

8. **Self-describing decision records** — Each record holds the original
   proposal, SHA-256 hashes of the diff and context, the detected layer,
   sampling settings, per-round hedge-demotion counts and any agent
   failure reasons, so a record can be matched to its fixture and
   re-run.

## Measured Production Precision (the honest part)

On synthetic fixtures, the reviewer scored 100% (3/3 golden, 0/5
false-positive rate across probe runs). On its first real workload —
a 300-line bridge refactor — blocker precision was **1/12 (~8%)**.
The gap was root-caused into classes, remediated with deterministic
guardrails, and re-measured on the same diff:

| Failure class | Baseline | After v1 | Status |
|---|---|---|---|
| Layer-rule misapplication (core rules on bridge code) | 7 | 0 | **Fixed** — layer metadata injection |
| Speculative phrasing filed as blockers | 3 | 0 | **Fixed** — taxonomy discipline; hedge guardrail in reserve |
| Confident-but-wrong assertions (missing context) | 0 | 4 | **Open** — dominant residual class; context injection is the designated remedy |

Total blockers fell 12 → 6 on the same diff; the one real defect
(`qttune_decode_signal()` hardcoded 8-byte buffer ignoring
`frame->data_length`) was caught in both runs and fixed in QtTune.
The re-measurement also surfaced the next finding honestly: the hedge
guardrail never fired because the contextual metadata changed the
reviewer's phrasing at the source — guardrails eliminated the classes,
context eliminated the rhetoric. The remaining failures are confidently
stated claims about code the reviewer cannot see, which no output
filter can fix.

Evidence: baseline `coach_artifacts/decision_debate_20261007_203917.json`,
re-measurement `coach_artifacts/decision_debate_20261009_014257.json`,
input `docs/fixtures/qttune_bridge_refactor.diff`, full analysis in
[ADR-0002](docs/decisions/0002-adjudication-and-fp-remediation.md).

Fixture-pass / production-fail is a known trap in eval harnesses. This
repo measures both — twice, with predictions recorded before each run.

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

## What Makes This Different From Tutorial Projects

| Typical "Multi-Agent" Repo | This Repo |
|---|---|
| Demo prompt → demo output | Eval harness with failure modes, remediation logs |
| Single run, cherry-picked | 5-run aggregates with variance reporting |
| Prompts hardcoded, no version | PROMPT_VERSION stamps every decision record |
| Only clean results shown | 8% precision published, root-caused, remediated, re-measured at 17% with class-level attribution |
| No evaluation methodology | Golden tests, probe logs, ADRs documenting decisions, model-free regression suite |
| "Works on my toy example" | Runs on actual codebase (QtTune), decision records archived |

## Transferable Patterns

These patterns work on ANY codebase:

- Derived verdicts → any merge-blocking review system
- Schema validation before judging → a malformed reply must never read as "no findings"
- Hedge demotion → enforce taxonomy discipline on any LLM output
- Layer/role metadata injection → applies wherever file-level rules differ
- Artifact-type prompting → headers vs. implementations differ everywhere
- Multi-run probes → stability is a property of the eval harness, not the model
- Measure → remediate per class → re-measure → publish the trend → this loop is the repo's core contribution

## Reproducing the Results

All numbers in docs/decisions/ are reproducible via the eval harness.
The probe_logs/ directory contains timestamped JSON artifacts for each
run. The probe and bake-off scoring were corrected on 2026-10-10 so that
parse failures and timeouts count against a model; ADR-0001's timeout
row predates a working timeout counter (details in STATUS.md). The
regression suite in tests/ runs without any LLM and is suitable for CI.

## Project Map and Continuation Notes

See [STATUS.md](STATUS.md) for a full file map, current state, open
issues, and notes for continuing development.

## Links

- QtTune Repository: https://github.com/erickramer42/qttune
- Ollama: https://ollama.com
