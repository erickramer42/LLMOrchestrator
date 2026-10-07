# Multi-Agent Review Tribunal

## TL;DR

A hand-rolled orchestration system for code review that uses adversarial
agents, deterministic guardrails, rule-based adjudication, and empirical
eval harnesses to produce verified merge decisions. Built to demonstrate
what's possible beyond LangChain/AutoGen abstractions — including
publishing its own measured failure rates and fixing them.

**Artifacts produced:** [Decision records](coach_artifacts/) *(incl. a real
300-line refactor debate)*, [Eval logs](probe_logs/),
[Bake-off results + measured precision data](docs/decisions/0001-model-selection.md),
[Input fixtures](docs/fixtures/)

## Prerequisites

- Python 3.11+
- Ollama (v0.40.0+) with local models pulled
- Git Bash or equivalent shell (Windows) / zsh/bash (Linux/macOS)

## Running Locally

Install dependencies and verify Ollama is up:

    pip install -r requirements.txt
    curl http://localhost:11434/api/version

Run the golden test suite (3 model fixtures + 7 deterministic guardrail
regression tests; the guardrail subset needs no LLM):

    python orchestrator.py --golden

Run the false-positive probe (defaults to core.h):

    python -m eval_harness.probe --model laguna-xs-2.1

Specify a custom fixture:

    python -m eval_harness.probe --fixture path/to/your/clean/header.h

Run a production debate on a real diff:

    python orchestrator.py --proposal "Describe the change" --diff path/to/change.diff

Review a header-only C ABI artifact (uses the header-scoped prompt):

    python orchestrator.py --proposal "Describe the header" --context path/to/header.h --header

## What This Actually Does

This isn't a demo — it was built to review
[QtTune](https://github.com/erickramer42/qttune), my cross-platform ECU
tuning application. The tribunal processes code diffs or full artifacts,
runs 3-round debates between a code reviewer and a domain expert agent,
passes their outputs through deterministic guardrails, and produces
structured decision records for downstream consumption.

Pipeline per round:

    AGENTS CRITIQUE INDEPENDENTLY
        → GUARDRAILS (hedge demotion, layer metadata)
        → RULE-BASED JUDGE (derived verdicts, fail-closed)
        → CONVERGED, or feedback fed back for another round

### Key Design Decisions

1. **Verdict derivation from content, not model labels** — Model
   self-reported verdicts exhibit run-to-run jitter. Merge decisions
   derive deterministically from blockers/questions counts (see
   `derive_verdict()` in orchestrator.py).

2. **Hedge-language demotion** — A blocker must be a demonstrable
   violation, stated with a line citation. Blockers phrased as speculation
   ("may", "might", "could", "needs verification") are deterministically
   demoted to the questions channel (`demote_hedged_blockers()`).
   Regression-tested against real production blocker texts — see
   `run_hedge_unit_tests()`.

3. **Layer-aware review context** — File paths are mapped to QtTune's
   layer structure (core / bridge / app) and injected into the transcript
   (file_metadata.py), so core-module rules (no Qt headers, C ABI purity)
   don't fire on bridge-layer code where Qt is legitimate.

4. **Prompt scoping by artifact type** — Header-only C ABI stubs vs.
   implementation code require different expectation levels (see
   `HEADER_SCOPE_CLAUSE` in reviewer_prompt.py).

5. **Multi-run eval probes over single-run benchmarks** — Variance is
   information. See probe_logs/ for 5-run aggregates.

6. **Parse failures fail closed** — Unusable reviews block merges rather
   than slipping through (see `call_agent()` retry logic).

7. **Prompts as versioned single source of truth** — PROMPT_VERSION
   stamps appear in every decision record, enabling correlation between
   eval results and production runs.

## Measured Production Precision (the honest part)

On synthetic fixtures, the reviewer scored 100% (3/3 golden, 0/5
false-positive rate across probe runs). On its first real workload —
a 300-line bridge refactor — blocker precision was **1/12 (~8%)**.
That gap is the most important result in this repo, and it was
root-caused into three classes:

| Failure class | Blockers | Status |
|---|---|---|
| Layer-rule misapplication (core rules on bridge code) | 7 | **Fixed** — layer metadata injection |
| Speculative phrasing filed as blockers | 3 | **Fixed** — hedge demotion guardrail |
| Definition-context guessing (struct internals unseen) | 2 | **Open** — queued as remediation #3 |

The one confirmed real catch (`qttune_decode_signal()` hardcoded 8-byte
buffer ignoring `frame->data_length`) was subsequently fixed in QtTune.
Evidence: `coach_artifacts/decision_debate_20261007_203917.json`,
input `docs/fixtures/qttune_bridge_refactor.diff`, triage in the ADR.
Re-measurement after remediation is pending — that's the next eval run.

Fixture-pass / production-fail is a known trap in eval harnesses. This
repo measures both.

## Running the Eval Harness

Command examples:

- Probe false-positive rate on clean headers:
  `python -m eval_harness.probe --model laguna-xs-2.1 --fixture ../qttune/core/include/qttune/core.h`
- Bake-off, detection vs. false positives:
  `python -m eval_harness.bakeoff laguna-xs-2.1 gemma4:12b`
- Diff-based review example (the archived debate):
  `python orchestrator.py --proposal "..." --diff docs/fixtures/qttune_bridge_refactor.diff`

## What Makes This Different From Tutorial Projects

| Typical "Multi-Agent" Repo | This Repo |
|---|---|
| Demo prompt → demo output | Eval harness with failure modes, remediation logs |
| Single run, cherry-picked | 5-run aggregates with variance reporting |
| Prompts hardcoded, no version | PROMPT_VERSION stamps every decision record |
| Only clean results shown | 8% production precision published, root-caused, remediated |
| No evaluation methodology | Golden tests, probe logs, ADRs documenting decisions |
| "Works on my toy example" | Runs on actual codebase (QtTune), decision records archived |

## Transferable Patterns

These patterns work on ANY codebase:

- Derived verdicts → any merge-blocking review system
- Hedge demotion → enforce taxonomy discipline on any LLM output
- Layer/role metadata injection → applies wherever file-level rules differ
- Artifact-type prompting → headers vs. implementations differ everywhere
- Multi-run probes → stability is a property of the eval harness, not the model
- Failure-mode documentation → context limits, timeout budgets, and
  thinking-token interactions are universal constraints

## Reproducing the Results

All numbers in docs/decisions/0001-model-selection.md are reproducible
via the eval harness. The probe_logs/ directory contains timestamped
JSON artifacts for each run. Guardrail regression tests run without any
LLM and are suitable for CI.

## Project Map and Continuation Notes

See [STATUS.md](STATUS.md) for a full file map, current state, open
issues, and notes for continuing development.

## Links

- QtTune Repository: https://github.com/erickramer42/qttune
- Ollama: https://ollama.com
