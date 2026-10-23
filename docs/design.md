# Design

How the tribunal works, and why it is built this way. For the measured
results see [results.md](results.md); for the full decision log see
[ADR-0002](decisions/0002-adjudication-and-fp-remediation.md).

## Pipeline

Each debate runs up to three rounds:

```
TRANSCRIPT (proposal + fenced diff/context + layer note + retrieved repo facts
            + prior-round feedback)
    → AGENTS CRITIQUE (same transcript; neither sees the other's reply)
    → SCHEMA VALIDATION (retry with a correction, then fail closed)
    → EVIDENCE CHECK (blockers that don't quote post-change code → questions)
    → HEDGE DEMOTION (speculative blockers → questions)
    → RULE-BASED JUDGE (verdicts derived from content, fail closed)
    → CONVERGED, or the critiques are fed back for another round
```

Before the first round, the input is checked. A run with no code, or a
request too large for the context window, ends before any model sees
it.

**Possible outcomes:**
- `APPROVED_FOR_MERGE`: neither agent has a blocker or an open item.
- `APPROVED_WITH_OPEN_QUESTIONS`: no blockers, but questions or concerns
  remain. They stay in the record.
- `MAX_ROUNDS_EXCEEDED - MANUAL_REVIEW_REQUIRED`: blockers survived
  three rounds.
- `AGENT_FAILURE - MANUAL_REVIEW_REQUIRED`: an agent produced no usable
  reply after its retries.
- `NO_INPUT - MANUAL_REVIEW_REQUIRED`: no diff and no context.
- `INPUT_TOO_LARGE - MANUAL_REVIEW_REQUIRED`: the request would leave
  the reply less than its full output cap.

The two agents have different jobs:
- **The code reviewer** (laguna-xs-2.1) has no loyalty to the project.
  It flags unsafe, buggy or untestable code. Each blocker is
  `{claim, file, quote}`.
- **The domain engineer** (gemma4:12b) argues from the project's intent
  and roadmap: J2534 and CAN-FD domain risks, and extensibility.

## Code layout

| Module | Purpose |
|---|---|
| `orchestrator.py` | CLI entrypoint: argument parsing and dispatch only |
| `config.py` | Models, runtime knobs, prompt composition |
| `agent_client.py` | Ollama client, the only module that touches the network. It retries invalid or schema-violating replies, then fails closed |
| `adjudication.py` | Pure logic: schema validation, verdicts, the evidence-quote check, hedge demotion |
| `debate.py` | Debate loop, input check, transcript templates, retrieval, judging, decision records; the measurement modes |
| `diff_reader.py` | The one unified-diff reader, shared by the evidence check, retrieval and layer mapping |
| `repo_context.py` | Offline indexer (typedefs, constants, call sites, file purposes) and diff-keyed retrieval |
| `reviewer_prompt.py` | Agent system prompts, versioned |
| `file_metadata.py` | File path → layer (core / bridge / app) |
| `golden_tests.py` | Golden suite: live-model fixtures and deterministic guardrail units |
| `eval_harness/` | FP-rate probe, model bake-off, and runners and scorers for round-1 and round-2 measurements |
| `tests/` | Deterministic regression tests, with Ollama faked at the HTTP layer |

The dependency direction is acyclic:
- prompts, layer maps and the diff reader are leaves;
- config composes the prompts;
- agent_client and adjudication are independent layers (callers hand
  adjudication's validators to the client as callbacks);
- repo_context, debate and golden_tests sit on top, and orchestrator is
  just the handle.

`adjudication.py` imports nothing with side effects. `tests/` fakes
Ollama at the HTTP layer, so the whole regression suite runs in CI
without any model.

## Key design decisions

1. **Verdicts come from content, not model labels.** A model's
   self-reported verdict jitters from run to run. The merge decision
   is derived from the blocker and question arrays (`derive_verdict()`
   in adjudication.py). A reply with missing or malformed arrays never
   reads as "no problems found".

2. **Blockers must quote their evidence.** Each reviewer blocker
   carries a quote of the code that shows the problem, as the code reads
   after the change. `demote_unverified_blockers()` moves a blocker to
   the questions channel when its quote is not in that file's
   post-change lines. This makes guessing expensive mechanically,
   instead of by asking the model for confidence.
   - Measured: valid stored blockers rose from 42% to 94% (ADR-0002,
     tenth measurement).
   - Known limit: a quote proves the code exists, not that it supports
     the claim.

3. **Hedged claims are questions.** A blocker must be a demonstrable
   violation. Blockers phrased as speculation ("may", "might", "could",
   "needs verification") are demoted to questions
   (`demote_hedged_blockers()`). The check reads the claim, not the
   quoted code, so a "may" in a quoted comment does not count. The rule
   is strict on purpose, even for a claim that quotes verified code.
   One measurement caught it demoting a hedged *true* claim. The claim
   stayed visible as an open question. The rule is regression-tested
   against blocker texts from real runs (`run_hedge_unit_tests()`).

4. **Unusable replies and unusable input fail closed.**
   - Invalid JSON, schema violations, timeouts and server errors are
     retried with a corrective message. If every attempt fails, the
     debate ends in manual review with the reason recorded.
   - Empty input, and a request too large for the context window, are
     refused before any model call.
   - Nothing unreadable can slip through as an approval.

5. **Reviewed code is fenced as data.** The diff and context sit between
   BEGIN DATA and END DATA lines whose mark is hashed from that input.
   So a comment in a reviewed diff cannot close the fence and pose as
   instructions. Truncated context says so.

6. **Retrieval gives reviewers facts, and the diff stays
   authoritative.** An offline indexer harvests type definitions,
   constants, file purposes and queued-connection call sites from the
   target repo. At review time, the entries tied to the diff go into
   the transcript under a character budget.
   - The pack is labelled a snapshot. Indexed entries the diff removes
     are omitted and named, not asserted. This came after a reviewer
     cited a line that existed only in a stale index.
   - The index stores each file's git blob id, and a review warns when
     the diff starts from a different version.
   - No output filter can fix a model confidently asserting facts it
     cannot see; only showing it the facts can.

7. **Layer-aware review context.** File paths map to QtTune's layers
   (core / bridge / app), and each layer's rules are injected into the
   transcript. So core-module rules (no Qt headers, C ABI purity) don't
   fire on bridge code, where Qt is legitimate.

8. **Prompts are scoped by artifact type.** Header-only C ABI stubs and
   implementation code get different expectations
   (`HEADER_SCOPE_CLAUSE` and `IMPL_SCOPE_CLAUSE` in reviewer_prompt.py).

9. **Prompts and judge rules are versioned.**
   - Every decision record carries `PROMPT_VERSION`.
   - It also carries a `prompt_fingerprint`, a hash of the exact
     templates used, which catches drift that a hand-bumped version
     string would miss.
   - A `judge_version` stamp does the same for the judge and guardrails,
     which change verdicts without changing any prompt.

10. **Decision records describe themselves.** Each record holds:
    - the original proposal and SHA-256 hashes of the diff and context;
    - the detected layer and the sampling settings;
    - per-round evidence and hedge demotion counts;
    - per-attempt token telemetry: prompt and output tokens,
      `done_reason` and wall time;
    - the exact retrieved context with its hash;
    - the input-size estimate;
    - any failure reasons.

    So a record can be matched to its fixture and re-run.

11. **Multi-run measurements over single runs.** Variance is
    information. Measurements take 10 samples of the reviewer's first
    round. Predictions are written into the ADR before each run, and
    the results go next to them, misses included.

## Transferable patterns

These carry over to any codebase:

- **Derived verdicts:** any merge-blocking review system.
- **Schema validation before judging:** a malformed reply must never
  read as "no findings".
- **Evidence-quoted findings, checked mechanically:** cheaper than
  asking a model to be careful.
- **Hedge demotion:** enforces taxonomy discipline on any LLM output.
- **Layer or role metadata:** wherever file-level rules differ.
- **Diff-keyed retrieval:** give reviewers indexed facts, not the whole
  repo, and never let a stale index overrule the diff.
- **Artifact-type prompting:** headers and implementations differ
  everywhere.
- **Measure, fix per failure class, re-measure, publish the trend:**
  this loop is the project's core contribution.
- **Forensic re-adjudication of eval ground truth:** when the code state
  behind your triage was wrong, your false-positive labels are wrong
  too.

To adapt the tribunal to another codebase, see
[portability_guide.md](portability_guide.md).
