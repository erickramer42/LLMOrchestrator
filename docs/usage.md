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
python -m unittest discover -s tests_mcp -v   # the MCP server; needs requirements-mcp.txt
```

The regression suite fakes Ollama at the HTTP layer, so the real client,
judge and debate code run without a model. CI runs `tests/` and the
compile check with `requirements.txt` alone, and again with
`tests_mcp/` and `requirements-mcp.txt` installed, each on Python 3.11
and 3.13.

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
and writes a decision record to `coach_artifacts/`. The exit status
follows the verdict, so a CI job or a hook can gate on it:

| Status | Meaning |
|---|---|
| 0 | Approved, with or without open questions |
| 1 | Blockers still stand after the last round |
| 2 | Usage error |
| 3 | No decision: an agent failed or the input was refused; a person must review it |

`--golden` exits 1 when any test fails. Run ad-hoc reviews
from a scratch directory if you don't intend to commit the record;
retrieval still works, since the index is read from next to
`retrieval.py`.

An accepted reviewer reply takes a median of 83 s on a local 12 GB GPU,
and a reply that thinks to the output cap a median of 266 s, so a full
three-round debate can take 10 minutes or more.

## MCP server

The same reviews, served to an MCP client over stdio
([ADR-0003](decisions/0003-mcp-server.md)). It needs the SDK on top of
the core's dependency:

```sh
pip install -r requirements-mcp.txt        # requests and mcp==2.3.0
python -m unittest discover -s tests_mcp -v
```

Register it with the client as a stdio server whose command is
`python <repo>/mcp_server`. The path must be absolute, since the client
starts the server from its own directory. Clients that read an
`mcpServers` file (a project's `.mcp.json`, for one) take this entry,
with the directories set explicitly:

```json
{
  "mcpServers": {
    "llm-orchestrator": {
      "command": "python",
      "args": ["/path/to/LLMOrchestrator/mcp_server"],
      "env": {
        "LLMORCH_RECORDS_DIR": "/path/to/LLMOrchestrator/mcp_records",
        "LLMORCH_INDEX_DIR": "/path/to/LLMOrchestrator/mcp_indexes"
      }
    }
  }
}
```

| Tool | What it does |
|---|---|
| `review_diff(proposal, diff, context?, header?, index_name?)` | Checks the input and queues a review; returns its `record_id` at once. Input that is empty or too large for the context window is refused and recorded at once. |
| `get_decision(record_id, wait_seconds?, include_record?)` | The review's `status` (`queued`, `running`, `done`, `failed` or `lost`), its round and agent while running, and once done the `final_verdict`, the final round's findings and `notes`. Waits up to 55 s, with progress notifications. |
| `list_decisions(limit?, since?)` | Recent reviews, newest first, with status, verdict and input hashes. |
| `verify_findings(diff, findings, context?, index_name?)` | Checks another reviewer's findings (`{claim, file, quote, id?}`) with the debate's guardrails, at once and without a model: each finding's outcome (`kept`, `quote`, `link`, `hedge` or `invalid`) and where its quote was found. No verdict on the change ([ADR-0005](decisions/0005-verify-findings.md)). |

Resources: `decision://{record_id}` (a finished record) and the committed
index's `index://info`, `index://files`, `index://types`,
`index://constants` and `index://callsites`. `get_decision`,
`list_decisions` and `verify_findings` are annotated read-only, and no tool reaches past the
server and its local models (`openWorldHint` false); clients use these
hints to decide when to ask before a call. The clients run against the
server so far, and what each run showed, are in
[mcp-clients.md](mcp-clients.md).

Only a `done` review has a verdict. Read its `notes` first:
`index_base_mismatch` means the repo context came from another version
of the files the diff changes. To review against the diff's own base,
build an index of it into the index directory and pass its file name:

```sh
mkdir -p mcp_indexes
python orchestrator.py --index <clone-at-base> --no-llm --index-out mcp_indexes/base.json
```

The server runs one review at a time and queues up to 4 more
(`LLMORCH_MAX_PENDING`); a call beyond that is refused as busy. Records go
to `mcp_records/` (git-ignored) or `LLMORCH_RECORDS_DIR`, never to
`coach_artifacts/`, and carry `metadata.interface` `{"name": "mcp",
"server_version": ..., "transport": ..., "caller": ...}`. A restart loses
queued and running reviews; `get_decision` then reports them as `lost`.

### Over HTTP

The same tools at `http://127.0.0.1:8765/mcp`, for a server shared by
several clients ([ADR-0004](decisions/0004-mcp-http-auth-audit.md)).
Every request needs a bearer token; mint one per client first. The token
is printed once, and the token file (`mcp_tokens.json`, git-ignored, or
`LLMORCH_TOKENS_FILE`) keeps only its hash:

```sh
python -m mcp_server token add laptop --scope review   # review includes read
python -m mcp_server token add dashboard --scope read
python -m mcp_server token list
python -m mcp_server token revoke dashboard            # takes effect at once
python -m mcp_server --http                            # 127.0.0.1:8765
```

A client sends `Authorization: Bearer <token>` on every request. In an
`mcpServers` file:

```json
{
  "mcpServers": {
    "llm-orchestrator": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {"Authorization": "Bearer <token>"}
    }
  }
}
```

| Refused | Answer |
|---|---|
| No token, an unknown one or a revoked one | HTTP 401, before the request is read |
| An `Origin` header the server doesn't allow (`LLMORCH_ALLOWED_ORIGINS`) | HTTP 403 |
| A `Host` header that doesn't name the server (`LLMORCH_ALLOWED_HOSTS`) | HTTP 421 |
| `review_diff` or `verify_findings` with a `read` token | Tool error `insufficient_scope` |
| More than 120 calls a minute (`LLMORCH_RATE_PER_MIN`) | Tool error `rate_limited` |
| More than 20 reviews an hour (`LLMORCH_REVIEWS_PER_HOUR`) | Tool error `rate_limited` |
| More than 2 of one caller's reviews queued or running (`LLMORCH_MAX_REVIEWS_PER_CALLER`) | Tool error `rate_limited` |

The limits are per token (per process over stdio) and reset on restart.
`verify_findings` counts only against the calls a minute, since it runs
no model.
`--host` other than loopback needs `--certfile` and `--keyfile`, or
`--insecure-http` to send tokens in clear text; the server also refuses
to start with no tokens.

Every tool call and resource read, on either transport, appends one line
to `mcp_records/audit.jsonl` (`LLMORCH_AUDIT_LOG`): the
time, the server version, the transport, the caller (the token's id, or
`stdio`), the tool and its arguments with `proposal`, `diff` and
`context` replaced by their SHA-256 and length and `findings` by the
SHA-256 of its JSON and its count, the outcome, the
review's id, status and verdict, the duration, for a finished review
the model token counts, and for `verify_findings` the outcome counts. A request refused before MCP gets a line with
its status, path and client address.

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

That fixture is the header the logs in `probe_logs/` were taken on; it
differs from Havne's current `core.h`.

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
debate sends (v11.1), and the feedback format of v9. Each
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
deterministic judge variants (gapped quotes, claim-quote linkage, k-of-n
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

**The corpus** (backlog #7): seven real Havne diffs in
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
python -m eval_harness.corpus score "coach_artifacts/measurement_engineer_*.json"
python -m eval_harness.corpus --manifest docs/fixtures/corpus_v2.json list   # corpus v2; run and score take it too
```

Corpus v2 (`docs/fixtures/corpus_v2.json`, `docs/fixtures/corpus_v2/`)
rebuilds the bug fixtures as forward diffs of the commits that
introduced each bug, so no removed line carries a fix's comment. Pass
`--manifest` before the subcommand; `replay --corpus` takes the same
option.

`score` reports, per fixture, blockers per run, each known bug's recall
(runs with a stored blocker whose claim names one of its symbols), bugs
found only among demoted blockers, and the blockers matching no known
bug, which are false-positive candidates to triage by hand. A symbol
match is a pointer, not a verdict: read the claim. With the hand labels
in `corpus_labels.json` it also prints the labeled summary; `--labels
none` prints the items alone, for labeling a new sample before scoring
it. It also prints the calls' cost (median first-attempt wall time,
attempts at the cap, failed calls) and warns when one fixture's records
come from several models. Engineer records are scored apart, with
`engineer_labels.json`: every blocker needs a label, and a concern or
question only when it states a known bug.

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
