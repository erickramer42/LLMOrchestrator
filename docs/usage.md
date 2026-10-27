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
`retrieval.py`.

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
python -m eval_harness.probe --model laguna-xs-2.1 --fixture docs/fixtures/qttune_core_e08b455.h
```

That fixture is the header the logs in `probe_logs/` were taken on.
QtTune's current `core.h` has changed since.

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

**Round-2 pairs** compare two round-2 formats: the CRITIQUES section a
debate sends since v11.1, and the feedback debates sent before it. Each
sample runs a debate's round 1, then the round-2 reviewer twice on the
same round-1 replies, once per format:

```sh
python -m eval_harness.round2 run --proposal "..." --diff docs/fixtures/qttune_bridge_refactor.diff --runs 10
python -m eval_harness.round2 score --diff docs/fixtures/qttune_bridge_refactor.diff \
    --symbols m_currentFrameCount "coach_artifacts/measurement_round2_*.json"
```

The scorer tags each round-2 blocker by where its subject first appeared
and counts each arm's first attempts that ran away (ADR-0002, eleventh
and twelfth measurements). The scorers expand globs themselves, so the
quoted patterns work in PowerShell too.

**Offline replay**, no model: re-judges archived round-1 replies under
deterministic judge variants (gapped quotes, claim–quote linkage, k-of-n
voting) and scores them with the hand labels in
`eval_harness/labels.json` (ADR-0002, thirteenth measurement):

```sh
python -m eval_harness.replay --diff docs/fixtures/qttune_bridge_refactor.diff --n 3 --k 2 \
    "coach_artifacts/measurement_round1_20261023_01*.json" \
    "coach_artifacts/measurement_round2_20261023_*.json"
```

It first checks that the current judge reproduces every record's stored
split. Records without labels are listed and left out. With `--corpus`
it does the same for corpus records, each judged against its own
fixture's diff and scored with `eval_harness/corpus_labels.json`:

```sh
python -m eval_harness.replay --corpus "coach_artifacts/measurement_round1_20261024_0*.json"
```

**The corpus** (backlog #7): seven real QtTune diffs in
`docs/fixtures/corpus/`, described by `docs/fixtures/corpus.json`. Five
are the reverse of a fix commit, so each introduces the bugs the commit
fixed, listed as its known bugs; two are forward diffs of commits no
later commit fixed. Each has the index of its own base, which `run`
passes as `--index-file`; its proposal is written in the diff's real
direction.

```sh
python -m eval_harness.corpus list                              # sizes, layers, input and base checks; no model
python -m eval_harness.corpus run --fixture all --runs 5        # round-1 samples, every fixture
python -m eval_harness.corpus run --fixture backoff_clamp_d1c20c0 --runs 5
python -m eval_harness.corpus run --fixture all --runs 5 --reviewer-model qwen3-coder:30b   # another reviewer
python -m eval_harness.corpus run --fixture all --runs 5 --engineer [--engineer-model gpt-oss:20b]   # the engineer's round-1 call alone
python -m eval_harness.corpus score "coach_artifacts/measurement_round1_*.json"
```

`score` reports, per fixture, blockers per run, each known bug's recall
(runs with a stored blocker whose claim names one of its symbols), bugs
found only among demoted blockers, and the blockers matching no known
bug, which are false-positive candidates to triage by hand. A symbol
match is a pointer, not a verdict: read the claim. With the hand labels
in `corpus_labels.json` it also prints the labeled summary; `--labels
none` prints the items alone, for labeling a new sample before scoring
it.

**The repair pass** (seventeenth and eighteenth measurements, not
shipped) can be re-run paired on archived replies:

```sh
python -m eval_harness.repair run --set corpus --dry    # what would be offered, no model call
python -m eval_harness.repair score --set corpus
python -m eval_harness.repair ceiling --set corpus      # the best any repair could do, no model
```

**Runaway repetition** (backlog #19), no model: for every attempt that
kept its whole thinking (those that hit the output cap or ran past
8,192 tokens), how much of it repeats earlier passages:

```sh
python -m eval_harness.runaway "coach_artifacts/measurement_round1_*.json"
python -m eval_harness.runaway repro coach_artifacts/measurement_round1_<id>.json --attempt 1 --dry
python -m eval_harness.runaway repro coach_artifacts/measurement_round1_<id>.json --attempt 1 --runs 2
```

`repro` re-sends one recorded round-1 attempt, with the corrections
before it and at its recorded temperature, after checking that today's
prompt matches the record's and that the rebuilt request has the
recorded size. Each run writes `coach_artifacts/measurement_runaway_<id>.json`.

Any review can use another index: `python orchestrator.py --index REPO
--no-llm --index-out PATH` writes one without touching
`repo_context.json`, and `--index-file PATH` on a review, or on
`round1 run` and `round2 run`, retrieves from it. The record names the
file under `metadata.repo_context_pack.index_file`.

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
