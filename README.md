# Multi-Agent Review Tribunal

## TL;DR

A hand-rolled orchestration system for code review that uses adversarial agents, rule-based adjudication, and empirical eval harnesses to produce verified merge decisions. Built to demonstrate what's possible beyond LangChain/AutoGen abstractions.

**Artifacts produced:** [Decision records](coach_artifacts/) *(incl. smoke test debate)*,
[Eval logs](probe_logs/), [Bake-off results](docs/decisions/0001-model-selection.md),
[Golden tests](gold_tests/)

## Prerequisites

- Python 3.11+
- Ollama (v0.40.0+) with local models pulled
- Git Bash or equivalent shell (Windows) / zsh/bash (Linux/macOS)

## Running Locally

Install dependencies and verify Ollama is up:
   pip install -r requirements.txt
   curl http://localhost:11434/api/version

Run the golden test suite:
   python orchestrator.py --golden

Run the false-positive probe (defaults to core.h):
   python -m eval_harness.probe --model laguna-xs-2.1

Specify a custom fixture:
   python -m eval_harness.probe --fixture path/to/your/clean/header.h

## What This Actually Does

This isn't a demo — it was built to review [QtTune](https://github.com/erickramer42/qttune), my cross-platform ECU tuning application. The tribunal processes code diffs, runs 3-round debates between a code reviewer and domain expert agent, and produces structured decision records for downstream consumption.

### Key Design Decisions

1. **Verdict derivation from content, not model labels** — Model self-reported verdicts exhibit run-to-run jitter. Merge decisions derive deterministically from blockers/questions counts (see orchestrator.py derive_verdict()).

2. **Prompt scoping by artifact type** — Header-only C ABI stubs vs. implementation code require different expectation levels (see reviewer_prompt.py HEADER_SCOPE_CLAUSE).

3. **Multi-run eval probes over single-run benchmarks** — Variance is information. See probe_logs/ for 5-run aggregates.

4. **Parse failures fail closed** — Unusable reviews block merges rather than slipping through (see call_agent() retry logic).

5. **Prompts as versioned single source of truth** — PROMPT_VERSION stamps appear in every decision record, enabling correlation between eval results and production runs.

## Running the Eval Harness

Command examples:
- Probe for false-positive rate on clean headers: python -m eval_harness.probe --model laguna-xs-2.1 --fixture ../QtTune/core/include/qttune/core.h
- Bake-off: detection vs. false positives: python -m eval_harness.bakeoff laguna-xs-2.1 gemma4:12b
- Production debate on real diff: python orchestrator.py --proposal "..." --diff path/to/diff --header

## What Makes This Different From Tutorial Projects

Typical "Multi-Agent" Repo | This Repo
--------------------------|----------
Demo prompt → demo output | Eval harness with failure modes, remediation logs
Single run, cherry-picked | 5-run aggregate with variance reporting
Prompts hardcoded, no version | PROMPT_VERSION stamps every decision record
No evaluation methodology | Golden tests, probe logs, ADRs documenting decisions
"Works on my toy example" | Runs on actual codebase (QtTune), decision records archived

## Transferable Patterns

These patterns work on ANY codebase:
- Derived verdicts → Works for any merge-blocking review system
- Artifact-type prompting → Headers vs. implementations differ everywhere
- Multi-run probes → Stability is a property of the eval harness, not the model
- Failure modes documentation → Context limits, timeout budgets, thinking-token interactions are universal constraints

## Reproducing the Results

All numbers in docs/decisions/0001-model-selection.md are reproducible via the eval harness. The probe_logs/ directory contains timestamped JSON artifacts for each run.

## Links

- QtTune Repository: https://github.com/erickramer42/qttune
- Ollama: https://ollama.ai
