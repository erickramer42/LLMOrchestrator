# ADR-0004: MCP Server over HTTP: Tokens, Audit Log and Limits

Date: 2026-11-19
Status: Accepted

## Context

ADR-0003's server runs over stdio: one client starts it as a child process,
and the operating system decides who can talk to it. Served over HTTP, it
becomes a shared service that any process able to reach the port can call.
A review holds the GPU for minutes, and its inputs are source code, so an
HTTP server needs to know who calls it, refuse callers it doesn't know
before any work starts, keep a record of every call, and stop one caller
from filling the queue.

What the MCP specification, revision 2026-07-28, says (read 2026-11-19):

- Authorization is optional. "Authorization is OPTIONAL for MCP
  implementations." When supported, "Implementations using an HTTP-based
  transport SHOULD conform to this specification", and STDIO
  implementations "SHOULD NOT follow this specification, and instead
  retrieve credentials from the environment."
  (https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization,
  Protocol Requirements)
- The Streamable HTTP binding: "Servers MUST validate the `Origin` header on
  all incoming connections to prevent DNS rebinding attacks", answering an
  invalid one with 403; "When running locally, servers SHOULD bind only to
  localhost (127.0.0.1)"; "Servers SHOULD implement proper authentication
  for all connections."
  (https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md,
  Security & Endpoint)
- For a locally run server, the security best practices list "Require an
  authorization token" as a way to restrict an HTTP transport.
  (https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices,
  Local MCP Server Compromise)

## Decision

### Transport

- `python -m mcp_server --http` serves the same tools and resources over
  Streamable HTTP at `/mcp`, through the SDK's `streamable_http_app` and
  `uvicorn` (both from the pinned SDK; no new dependency). Stdio stays the
  default.
- It binds to 127.0.0.1 unless `--host` says otherwise. A host other than
  loopback needs TLS (`--certfile`, `--keyfile`) or an explicit
  `--insecure-http`: a bearer token sent in clear text on a network is a
  shared secret given away.
- DNS rebinding protection is always on. The `Host` header must name the
  server (`host:port`, plus `localhost` on loopback, plus
  `LLMORCH_ALLOWED_HOSTS`); an `Origin` header, when present, must be one
  the server allows (the loopback origins, plus `LLMORCH_ALLOWED_ORIGINS`),
  else 403. Clients that send no `Origin` (non-browser clients) pass.

### Authentication: pre-shared bearer tokens with two scopes

- Every HTTP request needs `Authorization: Bearer <token>`; a missing,
  unknown or revoked token gets 401 from the SDK's bearer middleware, before
  the MCP request is read. The HTTP server refuses to start with no tokens.
- Stdio has no tokens, as the specification advises: the caller is the
  local process that started the server, recorded as `stdio`, with both
  scopes.
- Two scopes. `read` reads records, the index and the review status;
  `review` also submits reviews (it includes `read`, since a reviewer must
  read its own result). A call outside a token's scopes is a tool error
  (`insufficient_scope`) recorded in the audit log.
- Tokens are minted by `python -m mcp_server token add <id> --scope ...`,
  which prints the token once. The token file (`mcp_tokens.json` at the repo
  root, or `LLMORCH_TOKENS_FILE`; git-ignored) stores each token's id,
  scopes and SHA-256, never the token. A token is 32 random bytes
  (`secrets.token_urlsafe`), so an unsalted hash cannot be reversed by
  guessing; the comparison is constant-time. The file is reread when it
  changes, so `token revoke <id>` takes effect without a restart.

### Why tokens, and what the specification's OAuth flow would add

The specification's authorization is OAuth 2.1 with the MCP server as a
resource server. Implementing it would add:

- Protected Resource Metadata (RFC 9728) naming an authorization server,
  and that authorization server: OAuth 2.1, metadata discovery (RFC 8414 or
  OpenID Connect), client registration (pre-registered, Client ID Metadata
  Documents, or the deprecated dynamic registration).
- Audience-bound tokens: the server "MUST validate that access tokens were
  issued specifically for them" (RFC 8707 resource indicators), which
  rules out token passthrough.
- Short-lived tokens with refresh, a person behind each token (consent,
  identity from the authorization server), revocation at the
  authorization server, and step-up: a 403 `insufficient_scope` challenge
  naming the scope to request.

None of that is needed while one operator runs the server for a handful of
known clients, the reason the specification makes authorization optional.
A pre-shared token is a credential the operator hands out and revokes; the
audit log names the token on every call. What it gives up: tokens do not
expire, a token names a client and not a person, and a client cannot
discover how to get one. So this server does not claim the specification's
authorization: it serves no Protected Resource Metadata, and its 401
carries no `resource_metadata` parameter, so an OAuth client is not sent
to an authorization server that doesn't exist. The SDK requires an
`issuer_url` with any token verifier; it is set to the server's own URL
and never served.

The path to OAuth stays short: the token check is the SDK's
`TokenVerifier` interface. A verifier that validates JWTs or calls a token
introspection endpoint, with `resource_server_url` and `issuer_url` set,
replaces the token file without touching a tool. Implementing it is left
until the server is shared beyond one operator.

### Audit log

- One JSON line per tool call and resource read, appended to
  `audit.jsonl` in the records directory (or `LLMORCH_AUDIT_LOG`), and one
  line per HTTP request refused before MCP (401, 403, 421).
- A line holds: the UTC time; the server version; the transport; the
  caller (the token's id, or `stdio`, never the token); the method and the
  tool or resource; the arguments, with `proposal`, `diff` and `context`
  replaced by their SHA-256 and length; the outcome (`ok`,
  `tool_error`, `insufficient_scope`, `rate_limited`, `error`), with the
  review's id, status and verdict, or the first line of the error; the
  duration; and, for a finished review, the model token counts from its
  record.
- A refused HTTP request records the status, the path and the client
  address; it has no caller, since no token was accepted.
- The log is append-only from the server's side: opened for appending, one
  write per line under a lock. It is not tamper-evident: anyone who can
  write the file can edit it. It is git-ignored with the records.

### Limits

- Per caller: 120 calls a minute (`LLMORCH_RATE_PER_MIN`), 20 review
  submissions an hour (`LLMORCH_REVIEWS_PER_HOUR`), and 2 reviews queued
  or running at once (`LLMORCH_MAX_REVIEWS_PER_CALLER`), so one caller
  cannot fill the queue. A call over a limit is a tool error naming the
  limit and when to retry, and an audit line.
- The server-wide limits of ADR-0003 stay: one review on the GPU, and at
  most `LLMORCH_MAX_PENDING` waiting.
- The windows are in memory, so a restart resets them.

### Versioning

The server's version becomes 0.2.0; it is in every tool result, in the
server info a client reads at connection, and on every audit line.

## Consequences

- The core is unchanged; `mcp_server/` gains the HTTP entry point, the
  token store, and one middleware that checks scopes and limits and writes
  the audit line around every call, on both transports.
- The module-boundary rule (only `agent_client.py` sends network requests)
  is about the core's outbound calls. The HTTP server accepts inbound
  connections and lives in `mcp_server/`.
- TLS is passed through to `uvicorn`; the tests check that a non-loopback
  host without it is refused, not a TLS handshake.
- An operator who loses the token file loses every token; a new one is
  minted per client.
