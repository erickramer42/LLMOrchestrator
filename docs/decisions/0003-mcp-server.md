# ADR-0003: MCP Server

Date: 2026-11-19
Status: Accepted

## Context

The tribunal runs from the command line (`orchestrator.py`). An MCP server
lets an MCP client, such as an editor or a coding agent, submit a diff for
review and read the decision records, without the client knowing the
pipeline. Four facts about the pipeline shape the design:

- A debate is long. One accepted reviewer reply takes a median 83 s
  (STATUS, backlog #19), and a whole debate up to `MAX_DEBATE_ROUNDS`
  rounds takes about 12 minutes on the RTX 3060; one failing agent call
  can take 30 minutes. Many MCP clients end a tool call long before that.
- There is one GPU. Two debates at once would share it and slow each
  other.
- `coach_artifacts/` is evidence: a committed record needs its input
  fixture committed (evidence pairs), and ad-hoc reviews are not
  fixtures.
- The core needs only the standard library and `requests`, and the
  measurements in ADR-0001 and ADR-0002 depend on nothing else.

This ADR covers the stdio server. The HTTP transport, authentication and
the audit log, async model calls and a hosted-model adapter are later
steps with ADRs of their own.

## Decision

### The SDK and its pin

The server uses the official Python SDK, `mcp`, pinned exactly at 2.3.0
in `requirements-mcp.txt`.

- 2.3.0 was the newest release when this was written (released
  2026-10-02; https://pypi.org/project/mcp/2.3.0/ and
  https://github.com/modelcontextprotocol/python-sdk/releases, read
  2026-11-19). It requires Python 3.10 or newer, so CI's 3.11 floor holds.
- The 2.x line, not 1.x: 1.x receives only critical fixes, and 2.x speaks
  the current specification revision, 2026-07-28
  (https://modelcontextprotocol.io/specification/2026-07-28/changelog,
  read 2026-11-19), which an in-process client negotiates with this
  server.
- An exact pin, not a range: 2.x renamed the high-level server class
  (`FastMCP` to `MCPServer`) and changed other APIs, so a minor release
  may change behavior the tests rely on. An upgrade is a deliberate
  change with its test run.
- The cost: 2.3.0 brings 29 packages, `mcp-types==2.3.0`, `pydantic`,
  `anyio`, `starlette`, `uvicorn`, `sse-starlette`, `httpx2`, `PyJWT`,
  `cryptography`, `jsonschema` and `opentelemetry-api` among them, and
  `pywin32` on Windows. That is why it stays out of the core.

### A one-way package boundary

- `mcp_server/` is a package that imports the core (`debate`,
  `adjudication`, `retrieval`). No core module imports `mcp` or
  `mcp_server`; a test runs a debate import in a subprocess and checks
  that neither is loaded, as the indexer boundary is checked.
- `requirements.txt` stays the core's (`requests`); `requirements-mcp.txt`
  includes it and adds the pin. The CLI, the measurements and the golden
  suite work with the core's file alone.
- The folder is not named `mcp/`, which would shadow the SDK.
- The server's tests live in `tests_mcp/`. CI runs `tests/` in a job with
  the core's requirements only, which proves the core runs without the
  SDK, and `tests/` plus `tests_mcp/` in a job with both files. Nothing
  is skipped when a package is missing, so a broken install fails.
- A `pyproject.toml` with optional extras (`[mcp]`, and `[cloud]` if a
  provider SDK is ever needed) is left for the release step; the server's
  semantic version lives in `mcp_server/__init__.py` until then.

### Reviews are jobs

- `review_diff` checks the input, queues the review and returns its
  `debate_id` at once. One worker thread runs debates one at a time; a
  bounded queue holds the rest, and a call that finds the queue full gets
  a tool error saying the server is busy.
- Input the core refuses (no code, or a request past the context budget)
  is refused at submission, without waiting in the queue: the debate runs
  at once, makes no model call, and its record holds the refusal, as from
  the CLI. Input is never truncated.
- `get_decision(record_id)` reports a queued or running review's state
  (round and agent), or the finished record. It can wait up to 55 s for
  the review to finish, sending progress notifications while it waits, so
  a client need not poll in a tight loop.
- Jobs live in memory. At submission the server writes a pending marker
  next to the records; the debate's record replaces it. After a restart,
  a review whose marker has no record is reported as `lost`. An id with
  neither a marker nor a record is a tool error. Neither looks like a
  verdict.
- A review cannot be canceled. A running Ollama request cannot be
  interrupted, so a cancel could only discard the result; it is left out
  until it is needed.

### Results and failures

- Every verdict, `MANUAL_REVIEW_REQUIRED` ones included, is a normal tool
  result with `final_verdict` as a field of its structured output. A
  verdict is reported only from a finished record, and a review that has
  not finished has `final_verdict` null.
- A call the server cannot serve (bad arguments, an unknown id, an
  unreadable record, a full queue) is a tool error (`isError`). A server
  fault while a queued review runs (an exception from the debate, such as
  a records directory that cannot be written) ends that review as
  `failed`, with the error and no verdict; the marker keeps that answer
  across a restart. Model failures are not server failures: the core
  fails closed and the record says `AGENT_FAILURE - MANUAL_REVIEW_REQUIRED`.
- Neither path can produce an approval; a test sends schema-invalid model
  replies and an unreachable model through the server and checks for
  `AGENT_FAILURE`.

### Records and provenance

- Server reviews write their records to `mcp_records/` at the repo root,
  or to the directory in the `LLMORCH_RECORDS_DIR` environment variable.
  The path never depends on the working directory, since a client starts
  a stdio server from anywhere. `mcp_records/` is git-ignored: these are
  not evidence pairs. The CLI keeps writing to `coach_artifacts/`.
- A record's `metadata.interface` names the entry point: `{"name":
  "cli"}`, or `{"name": "mcp", "server_version": ...}`. Records written
  before this ADR lack the field and are CLI runs.

### Stdout is the transport

Over stdio, stdout carries the protocol. The server imports `debate`,
never `orchestrator.py`, which prints its results to stdout; the core's
warnings and the client's retry notes go to stderr. A test runs a review
through the server with stdout captured and checks that nothing reached it.

### The index

- A review retrieves from the committed index by default. It is built
  from the bridge fixture's base, `e0c4c31`, so most other diffs will not
  match it; the debate records the mismatch, and the tool's result puts
  `index_base_mismatch` first among its notes.
- `index_name` selects an index by file name from one directory,
  `mcp_indexes/` at the repo root or the directory in
  `LLMORCH_INDEX_DIR`. A name with a path separator or a leading dot is
  refused, so a call cannot read an arbitrary file.

### Input safety

- The diff, context and proposal arrive as text, never as paths.
- A record id is checked against the debate-id pattern before any file
  name is built from it.
- Each text field is capped at 200,000 characters before the input check
  runs; the input check then refuses what the context window cannot hold.

### Tools and resources

The server offers `review_diff`, `get_decision` and `list_decisions` as
tools, and the finished records (`decision://{record_id}`) and the
committed index's sections (`index://info`, `index://files`,
`index://types`, `index://constants`, `index://callsites`) as read-only
resources. Records are both a tool and a resource because client support
for resources varies; the tool is the path every client has.

### Which models run

The server runs the models in `config.py` on the local Ollama, as the CLI
does. It never falls back to another provider when Ollama is down: the
run fails closed. MCP sampling (asking the client's model) is not used:
the client chooses that model and may ignore the requested temperature,
so a record could not say what produced its verdict. If a hosted-model
provider is added, the records stamp the provider and model, and results
are compared only between runs on the same provider; every number in
ADR-0001 and ADR-0002 is from the local models.

## Consequences

- The core's dependencies and the measurements are unchanged. The core
  gains four optional parameters on `run_debate` (a record id, a records
  directory, a progress callback, the interface stamp) and a public input
  check; the debate fingerprint and the requests a debate sends do not
  change, and tests pin that.
- A server restart loses queued and running reviews; they are reported as
  `lost`, and a client resubmits them.
- Server reviews are not evidence. A review worth keeping becomes a
  fixture under `docs/fixtures/` and is rerun from the CLI.
