# Adapting the Tribunal to Another Codebase

The judging machinery is codebase-independent: derived verdicts, schema
validation, evidence-quoted blockers, the hedge check and fail-closed
handling work on any diff. What is specific to QtTune is the domain
knowledge: the engineer's priorities, the layer rules, the indexer's
harvest and the fixtures. This guide lists each piece and where it
lives. Moving these behind configuration is backlog #10.

## What to change

| Piece | Where | What to do |
|---|---|---|
| Models | `MODELS` in [config.py](../config.py) | Set `code_reviewer` and `auto_engineer` to models you have pulled. Keep `NUM_CTX` large enough for the prompt plus the reviewer's thinking (see below). |
| The engineer's domain | `AUTO_ENGINEER_PROMPT` in [reviewer_prompt.py](../reviewer_prompt.py) | Replace the automotive and J2534 priorities with your domain's: its risks, roadmap and compliance concerns. Keep the output schema (blockers, concerns, questions). |
| The reviewer's standards | `REVIEWER_SYSTEM`, `IMPL_SCOPE_CLAUSE` and `HEADER_SCOPE_CLAUSE` in `reviewer_prompt.py` | Adjust the rules a reviewer applies to implementations and to interface-only files. Keep the `{claim, file, quote}` blocker schema: the evidence check depends on it. |
| Layer rules | `identify_layer` and `get_layer_constraints` in [file_metadata.py](../file_metadata.py) | Map your directory layout to layers and write each layer's rules. A layer whose rules differ (for example, a library that must stay framework-free) is where this pays off. |
| The repo index | [indexer.py](../indexer.py) | It harvests C and C++ typedefs, constants and Qt queued-connection call sites. For another language, adapt the harvest, or run without an index: retrieval is optional and never fatal. |
| Fixtures | [review_fixtures.py](../review_fixtures.py) and `CASES` in [eval_harness/bakeoff.py](../eval_harness/bakeoff.py) | Replace the snippets with your codebase's known failure modes and clean reference code. |
| A corpus | `docs/fixtures/corpus.json` and [eval_harness/corpus.py](../eval_harness/corpus.py) | Reverse a few of your own bug-fix commits: each reverse diff reintroduces a known bug, which gives recall. Add one or two clean forward diffs for a false-positive rate. |

Every change to a prompt, a layer note or the pack format bumps
`PROMPT_VERSION`, so records stay comparable.

## What to keep

These are the parts that make the output trustworthy; the reasons are
in [design.md](design.md).

- **Derived verdicts:** never use a model's self-reported verdict.
- **Evidence-quoted blockers,** checked against the diff.
- **Hedged blockers become questions.**
- **Fail closed:** an unusable reply or input ends in manual review.
- **Versioned prompts and judge rules,** stamped into every record.
- **Multi-sample measurement:** single runs are anecdotes.

## Validating a new setup

1. Run the regression suite: `python -m unittest discover -s tests`.
   It needs no model and must stay green.
2. Probe a clean file from your codebase to see the false-positive
   floor:
   `python -m eval_harness.probe --model <reviewer> --fixture path/to/clean_file`.
3. Run the bake-off on your fixtures:
   `python -m eval_harness.bakeoff <reviewer> <engineer>`.
4. Sample round-1 reviews on a real diff and label them by hand:
   `python -m eval_harness.round1 run --proposal "..." --diff your.diff --runs 10`.
   Clean fixtures are not enough: this project scored 100% on synthetic
   fixtures and 17% on its first real diff.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Many false blockers on clean code | Rules too aggressive for the code under review | Check the layer mapping first; rules for the wrong layer were the first false-positive class here. |
| Replies cut off, parse failures | Thinking fills the output budget | Read the record's `telemetry`. If an attempt hit `NUM_PREDICT`, the model was looping and the retry usually recovers; raise `NUM_CTX` only if finished replies do not fit (ADR-0001). |
| Timeouts | Model too large for the GPU, or too long a context | Use a smaller model or a smaller `NUM_CTX`, keeping room for the prompt plus thinking. |
| Valid blockers demoted to questions | Quotes from removed lines | Expected for bugs that delete code; see [results.md](results.md). |
| Many bugs missed | Model too small for the task | Compare models on your corpus before tuning prompts. |
