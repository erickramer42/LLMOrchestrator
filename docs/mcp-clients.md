# MCP Client Compatibility

Which MCP clients have been run against the server
([ADR-0003](decisions/0003-mcp-server.md),
[ADR-0004](decisions/0004-mcp-http-auth-audit.md)), what each run
checked, and what it showed. A row comes from a run, dated, never from a
client's documentation; what was read in a client's source and not yet
run is listed apart. Commands and settings are in
[usage.md](usage.md#mcp-server).

## Runs

| Client | Its MCP library | Transports | Server | Date | Result |
|---|---|---|---|---|---|
| Python SDK client (`tests_mcp/`) | `mcp` 2.3.0 | in-process, stdio, HTTP | every version | each CI run | Every tool, resource and refusal; the regression suite |
| MCP Inspector 2.13.0, CLI mode | `@modelcontextprotocol/client` 2.4.0 | stdio, HTTP | 0.2.0; annotations at 0.2.1 | 2026-11-19 | 18 of 18 checks as designed |

No client has yet run a review through to a model verdict: every check
above either stops before a model call or uses the fake model.

## MCP Inspector 2.13.0

Run 2026-11-19 on Windows with Node.js 24.5, from the command line
(`npx -y @modelcontextprotocol/inspector@2.13.0 --cli ...`), against
server 0.2.0. No check called a model: the one review submitted had no
code, which the server refuses and records without a model call.

Over stdio, 11 checks:

| Check | Result |
|---|---|
| `tools/list --strict` | Three tools; no schema portability problems (exit 0) |
| `resources/list`, `resources/templates/list` | The five `index://` resources; `decision://{record_id}` |
| Read `index://info` | The committed index's version and source commit |
| `list_decisions` on an empty server, then with `limit=5` | `[]`; then the refused review |
| `review_diff` with no code | `done`, `NO_INPUT - MANUAL_REVIEW_REQUIRED`, `rounds_completed` 0 |
| `get_decision` and read `decision://` for that review | The summary and the full record |
| `get_decision` with `../x` | Tool error: not a review id |
| `review_diff` with `index_name=../x.json` | Tool error: a file name with no path |

Over HTTP, with a `review` token and a `read` token, 7 checks:

| Check | Result |
|---|---|
| `tools/list` with the review token | The three tools |
| `tools/list` with no token, and with a wrong one | Refused (HTTP 401); the Inspector reports that the server needs OAuth |
| `list_decisions` with the read token | Allowed |
| `review_diff` with the read token | Tool error `insufficient_scope` |
| `review_diff` with no code, review token | Refused input recorded, caller `insp-review` |
| Read `index://types` with the read token | Allowed |

The audit log held one line per call and one per refused request, and
neither token. Rerun at 0.2.1, `tools/list --strict` showed each tool's
annotations and still no schema problems.

What the run showed about clients:

- An OAuth-first client treats a 401 as a sign-in prompt, even with no
  Protected Resource Metadata to follow. A client must be given its
  token before it connects; it cannot discover how to get one
  ([ADR-0004](decisions/0004-mcp-http-auth-audit.md), "Why tokens").
- The Inspector connected with the initialize handshake and a session,
  where the Python SDK client uses the stateless 2026-07-28 protocol.
  The server answered both.
- In `--cli` mode, `--tool-arg` and `--header` take several values, so
  the server command or URL follows `--`.
- Once, after printing a correct result, the Inspector process exited on
  a Node.js assertion (`src\win\async.c`); the server was unaffected.

## Read, not yet run

### Lumo Desktop

From the source of Lumo Desktop at `bd5e2c6` (2026-11-17,
https://github.com/ProtonLumo/lumo-desktop, read 2026-11-19); no run yet:

- Its MCP client is `rmcp` 3.5.1, the Rust SDK, and connects with the
  initialize handshake.
- A custom server runs over stdio (command, arguments, environment) or
  HTTP. An HTTP server takes OAuth, a static `Authorization: <scheme>
  <secret>` header, several static headers, or none; secrets are kept in
  the operating system's keychain. The server's bearer tokens fit the
  static header.
- Connections are made by the desktop app, so a loopback server is
  reachable.
- A tool call times out after 60 s, above `get_decision`'s 55 s wait.
- It reads tools only: no resources, progress notifications or server
  instructions. Its model learns the submit-then-poll pattern from the
  tool descriptions, which therefore state it, and reads a record
  through `get_decision` with `include_record`.
- Tools of a server not on its vetted list always need approval;
  annotations change that only for vetted servers.
- Its model runs on Proton's servers, so tool results (findings, record
  summaries) leave the machine; the review itself runs on the local
  models.
