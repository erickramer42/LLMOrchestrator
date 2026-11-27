# ADR-0006: A Task Board for Work Between Agents

Date: 2026-11-26
Status: Accepted

## Context

Havne's coding sessions run on a paid hosted model, and checking another
reviewer's findings in the code is where one of them spends the most
tokens: a read-only cold read of a diff costs it roughly 50-100K tokens.
Lumo is a hosted model on a flat-cost plan with a window of about 271K
tokens, weaker than the paid model at refinement, and already an MCP client
of this server (docs/mcp-clients.md). It reads the projects folder through
its own file access, and no Lumo API is available (Proton's roadmap of
2026-10-15 announces one with no date). So the server cannot call Lumo; Lumo
has to pull work, and what it returns has to be checked before anyone uses
it.

The repo is public, so the design has to work for anyone who clones it: no
shared server process, no client registration per project, no paths of one
machine in committed files.

## Decision

### The board

The `tasks` package keeps one JSON record per task under
`<records>/tasks/` (`mcp_records/` by default, git-ignored, or
`LLMORCH_RECORDS_DIR`). A task is `open`, `claimed`, `done` or `failed`.
Every change to a record holds the task's lock file, created exclusively,
so of two workers claiming at once exactly one gets the task (pinned by a
test). Every process that names the same directory shares the board.

It has two front ends over the same store. Submitters use the command line,
`python -m tasks submit|list|get|claim|submit-result`, so a session with a
shell needs no MCP registration and carries no tool descriptions. Workers
with MCP use three server tools: `list_tasks`, `claim_task` and
`submit_result`. The core package never imports `mcp` (pinned by a test).

### Projects

A git-ignored `projects.json` names each project: its root, its rule
folder (files whose `paths:` frontmatter says which sources they cover),
the files every task lists, its denylist, and paths a task never lists.
`projects.example.json` shows the shape. A task lists the files its
findings cite, the project's always-listed files, and the rules whose globs
match a cited file.

### Pinned inputs

A task names the work branch's commit. A claim finds the checkout (a
worktree or the main clone) whose HEAD is that commit and refuses when none
is, or when a listed tracked file has uncommitted changes there. The claim
returns, in one result, the instructions, the findings and each file's path
to read it from; Lumo reads them itself. A file git does not track (such as
a git-ignored rule) is read from the main clone's working tree, and its
SHA-256 is recorded at the claim. Git runs with `--no-optional-locks`, so
the board never rewrites the index of a tree other sessions build in.

### The checks

The first kind is `second_read` (version `sr1`): for each finding the
worker answers `supported`, `refuted` or `unclear`, and a supported or
refuted item carries a file, a quote and a one-sentence reason. Each such
item is judged by `adjudication.judge_finding`, the check `verify_findings`
and the debates use, with the reason as the claim: its quote must be in the
named file as it reads at the task's commit (`adjudication.file_sources`),
and its reason must not hedge. Whole files have no hunks, so claim-quote
linkage does not apply. A quote from a git-ignored file whose hash changed
since the claim is not checked and fails. An unclear item needs no quote and
is reported as unclear.

A failing item goes back once with its reason; the items that passed stand.
After the retry it is reported as unverified, never as a verdict. An answer
with no usable item twice fails the task. The submitter gets back only the
checked items, the unclear ones, and what failed or went unanswered.

### What leaves the machine

Lumo reads the project directly, unmasked: Proton states zero-access
encryption and no logging for Lumo, and it is treated as a private route
(decided 2026-11-26). The board itself checks
what it sends: the task's text at submission and the result before the
submitter sees it are matched against the project's denylist (one
case-insensitive regex per line); a match refuses the task or fails it
without a result. A configured denylist that is missing refuses every task.

### Cost

Each record counts characters: the submission, every result the submitter
fetched, every claim bundle and every answer, plus the tokens the
submitter reports (`get --caller-tokens`). These are what the first
measurement compares with a cold read by a hosted-model session.

### Scope, limits and versions

`claim_task` and `submit_result` need the review scope, `list_tasks` the
read scope; none takes a review slot. An answer's items reach the audit log
by hash and size only, as findings do. Each record stamps `BOARD_VERSION`
(`b1`), the kind's version and `JUDGE_VERSION`. `file_sources` is new and
changes nothing a debate or `verify_findings` judges, so `JUDGE_VERSION`
is unchanged. The server's version becomes 0.4.0.

## What is not known

- How often Lumo's items pass the checks, and how often a passed item is
  right. Its first runs need a prediction in ADR-0002 before the first
  sample.
- Whether the board saves the submitter tokens at all against a cold read
  by a hosted-model session; the saving is measured on Lumo's next real
  cold read before more kinds are built.
- Whether one retry recovers enough items to be worth the second round.

## Consequences

- A task waits until someone tells Lumo to claim it, and Lumo asks for
  approval on each tool call of an unvetted server. The board is for
  batched reads, never for gating a merge.
- Nothing notifies the submitter; it reads the result with `get`, which
  can wait.
- A new kind is a registry entry in `tasks/kinds.py` (payload, files cited,
  item shape, instructions, version), not a new tool.
