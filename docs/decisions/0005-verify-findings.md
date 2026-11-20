# ADR-0005: Checking Other Reviewers' Findings

Date: 2026-11-19
Status: Accepted

## Context

The tribunal's guardrails are deterministic (ADR-0002): the evidence check
demotes a blocker whose quote is not in the post-change code of the file it
names, claim-quote linkage (j8) demotes one whose claim names code
identifiers none of which is in the quote's hunk, and the hedge check
demotes a hedged claim. They read a blocker's claim, file and quote and the
diff; they do not depend on which model wrote the blocker. Other reviewers
(other review tools, other models, people) report findings without such
checks. Running the guardrails on their findings needs no model and no GPU,
and takes milliseconds.

## Decision

### The tool

The MCP server gains `verify_findings(diff, findings, context?,
index_name?)`. Each finding is an object `{claim, file, quote, id?}` in the
reviewer's blocker shape (`reviewer_prompt.py`), with an optional `id` the
caller gets back. The result gives each finding its outcome, what the
outcome means, and where its quote was found:

| Outcome | Meaning |
|---|---|
| `kept` | A blocker: its quote is in the post-change code, its claim names code of the quote's hunk or none, and it is not hedged |
| `quote` | Demoted by the evidence check: no quote of 8 or more characters found in the named file's post-change lines or in the context |
| `link` | Demoted by claim-quote linkage |
| `hedge` | Demoted by the hedge check |
| `invalid` | Dropped by normalization: no content |

The call is synchronous: it writes no record, starts no job and calls no
model.

### The same checks as a debate

`adjudication.judge_finding` judges one blocker as a debate's round 1
judges a reviewer blocker: normalization, the evidence check with
linkage, then the hedge check. The golden suite's judge cases call it
too, so every judge case also pins the tool. Each check judges a blocker
without regard to the others, so judging findings one at a time equals
judging them as one reply; a test pins this against every archived j8
round-1 record under `coach_artifacts/`, where each blocker must end
where its record stored it. On 2026-11-19 the test covered 826 of the
828 blockers in those records. The other 2 carry a field the model added
(`quote2`): a record stores a blocker as flattened text, which cannot be
split back into its fields once there are more than three, so the test
skips them. `JUDGE_VERSION` is unchanged, since no debate's verdict moves.

Three choices differ from a debate on purpose:

- Only `claim`, `file` and `quote` are read. The hedge check reads every
  field of a blocker but its quote, so a caller's severity or suggestion
  text ("this could use a mutex") would otherwise demote the finding.
- The context is read whole. A debate checks quotes against the first
  8000 characters, which is what its reviewer was shown; another reviewer's
  view is not known.
- With no `index_name` the committed index supplies the type and constant
  names, as for `review_diff`. They matter only to linkage's rule for
  capitals-only tokens, and no base check is made.

### No verdict on the change

`derive_verdict` returns `approve` for a reply with no blockers and no open
items, so an empty findings list, or one whose findings were all dropped,
would read as an approval of a diff nobody checked. The tool returns
outcomes and counts and no verdict, and every result's `notes` says that
the outcomes judge the findings, not the change. A call with no diff and no
context is refused, since there is no code to check a quote against.

### Scope, limits and the audit line

- The tool needs the `review` scope: like `review_diff`, it takes code and
  claims about it from the caller. Over stdio the caller has both scopes.
- It is not counted against the GPU limits of ADR-0004 (reviews an hour,
  a caller's share of the queue); the per-minute call limit applies.
- At most 100 findings a call, 20,000 characters for a claim or a quote,
  and `review_diff`'s caps for the diff and context.
- Its audit line records the findings as the SHA-256 of their JSON and
  their count, never their text, and the outcome counts.
- No model reads the findings, so text in them cannot instruct anything;
  the checks read it as data.

### Versioning

The server's version becomes 0.3.0.

## What is not known

The guardrails' precision is measured on this project's reviewer replies
(ADR-0002). On other reviewers' findings it is not measured. Two failure
modes are expected: a finding that cites a line number instead of quoting
code ends as `quote`, and hedged wording, common in other reviewers' prose,
ends as `hedge`, whether the finding is right or not. Until a measurement
registered in ADR-0002 scores the outcomes against hand labels, a demotion
says that a finding failed a check, not that it is wrong.

If that measurement shows line citations to be the main cause of
demotion, one remedy is to resolve a cited post-change line to its text
before the quote check. That changes what the evidence check sees, so it
is a judge change (`JUDGE_VERSION`, an ADR-0002 section). It fails closed:
a line outside the diff's post-change lines, a removed line, a file the
diff does not touch or an ambiguous range stays demoted. The result
records which findings were resolved from a line number.

## Consequences

- `adjudication.py` gains `index_symbols` (from `debate.py`),
  `judge_finding` and `verify_findings`, all pure; the core has no new
  dependency and still never imports the server.
- `mcp_server/guard.py` separates the tools that need the `review` scope
  from the ones that use the GPU, and hashes a findings list in the audit
  line.
- Writing these tests found that a limit set to 0 raised an internal error
  instead of refusing; a limit of 0 now refuses every call it covers.
