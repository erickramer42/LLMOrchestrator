# Usage

Every command runs from the repo root. Output directories
(`coach_artifacts/`, `probe_logs/` and `gold_tests/`) are relative to the
working directory.

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) v0.40.0+, with the models named in
  `MODELS` in [config.py](../config.py) pulled
- A Bash-style shell (Git Bash on Windows, or bash/zsh)

```sh
pip install -r requirements.txt            # one dependency: requests
curl http://localhost:11434/api/version    # Ollama must be up for anything model-backed
```

## Tests (no model needed)

```sh
python -m unittest discover -s tests -v
python -m py_compile *.py eval_harness/*.py tests/*.py
```

The regression suite fakes Ollama at the HTTP layer, so the real client,
judge and debate code run without a model. CI runs both commands on
Python 3.11 and 3.13.

## Reviews

Review a diff:

```sh
python orchestrator.py --proposal "Describe the change" --diff path/to/change.diff
```

Review a header-only C ABI artifact with the header-scoped prompt:

```sh
python orchestrator.py --proposal "Describe the header" --context path/to/header.h --header
```

`--proposal` needs `--diff` or `--context`. Each run prints a JSON summary
and writes a decision record to `coach_artifacts/`. Run ad-hoc reviews
from a scratch directory if you don't intend to commit the record;
retrieval still works, since the index is read from next to
`repo_context.py`.

A reviewer call on a local 12 GB GPU takes about 1–4 minutes, so a full
three-round debate can take 10 minutes or more.

## Golden suite

3 live-model fixtures and 7 deterministic guardrail units. Each fixture
is reviewed as a debate's first-round reviewer reviews it, evidence check
included:

```sh
python orchestrator.py --golden
```

The run log goes to `gold_tests/run_*.json`. Live results vary from run
to run; the unit tests are the pass/fail signal.

## Repo context index

Build the context pack that reviews retrieve from. `--no-llm` skips the
LLM purpose summaries:

```sh
python orchestrator.py --index ../qttune --no-llm
```

The index describes one tree. Index the commit a diff starts from: a
review warns when the diff's base differs from the indexed files.

## Eval harness

**False-positive probe** on a clean fixture. It classifies the model as
CLEAN, BORDERLINE or SYSTEMATIC, or NO DATA when every run times out or
fails to parse; failed runs count against the model.

```sh
python -m eval_harness.probe --model laguna-xs-2.1 --fixture ../qttune/core/include/qttune/core.h
```

**Bake-off**, detection against false positives. A parse failure or
timeout on a bug case counts as a miss.

```sh
python -m eval_harness.bakeoff laguna-xs-2.1 gemma4:12b
```

**Round-1 measurements**, the samples the measurements score. Each
sample is exactly the reviewer call a debate's first round makes,
saved as `coach_artifacts/measurement_*.json`:

```sh
python -m eval_harness.round1 run --proposal "..." --diff docs/fixtures/qttune_bridge_refactor.diff --runs 10
python -m eval_harness.round1 score --diff docs/fixtures/qttune_bridge_refactor.diff \
    --symbols SignalListModel,MaxInFlightFrames,m_inFlightFrames --repo ../qttune --rev 8ffbf19 \
    "coach_artifacts/measurement_round1_*.json"
```

The scorer keeps first attempts on that exact diff. It counts blockers
naming the given symbols and lists candidates for hand review: blockers
naming code the diff removed that the post-change tree lacks (ADR-0002,
fifth measurement).

**Round-2 pairs** compare a feedback format with a debate's own. Each
sample runs a debate's round 1, then the round-2 reviewer twice on the
same round-1 replies, once per format:

```sh
python -m eval_harness.round2 run --proposal "..." --diff docs/fixtures/qttune_bridge_refactor.diff --runs 10
python -m eval_harness.round2 score --diff docs/fixtures/qttune_bridge_refactor.diff \
    --symbols m_currentFrameCount "coach_artifacts/measurement_round2_*.json"
```

The scorer tags each round-2 blocker by where its subject first appeared
(ADR-0002, eleventh measurement). The scorers expand globs themselves, so
the quoted patterns work in PowerShell too.

## Reading a decision record

```sh
python -c "
import json, glob
r = json.load(open(max(glob.glob('coach_artifacts/decision_*.json')), encoding='utf-8'))
print(r['outputs']['final_verdict'])
for h in r['outputs']['round_history']:
    for role, calls in h['telemetry'].items():
        for c in calls:
            print(h['round'], role, c['attempt'], c['prompt_eval_count'], c['eval_count'],
                  c['done_reason'], c['wall_s'], c['outcome'][:60])
"
```

Each line is one model call: round, agent, attempt, prompt and output
tokens, why generation stopped, wall time and outcome.
