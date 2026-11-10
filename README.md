# Multi-Agent Code Review Tribunal

Two local LLMs review a code change, and deterministic Python decides
whether it can merge. I built it, without an agent framework, to review
[Havne](https://github.com/erickramer42/havne), my OBD-II scan tool and
data logger. It is measured on real Havne diffs: each change's
prediction is written before its run, and the failures are published
beside the fixes.

## Highlights

- Two models on one 12 GB GPU, served by Ollama, review each diff: a
  code reviewer (laguna-xs-2.1) and a domain engineer (gemma4:12b).
- Verdicts are derived from what the agents wrote, never the label they
  report; a blocker stands only if its quote is in the diff and its
  claim doesn't hedge ([adjudication.py](adjudication.py)).
- On the first real diff, 2 of 12 blockers were correct (17%). Fixed
  one failure class at a time, 30 of 32 are valid (94%, 19 samples).
- From that diff alone, the reviewer found two bugs Havne had shipped
  and later fixed: a data race on a frame counter and a freeze past
  10,000 frames ([results](docs/results.md#two-real-bugs-found-from-a-diff-alone)).
- Changes are measured like experiments: the prediction and ship rule
  are written before the first sample, labels before scoring, and
  failed changes are published with their reasons.
- The regression tests fake Ollama at the HTTP layer, so the real
  client, judge and debate code run with no model, in CI on Python 3.11
  and 3.13 ([tests/](tests/)).

## How it works

```
 diff + context --> transcript: code fenced as data, layer rules,
                    facts retrieved from an index of the repo
                              |
              +---------------+---------------+
              |                               |
        code reviewer                  domain engineer      local LLMs,
              |                               |             same transcript
              +---------------+---------------+
                              v
   schema validation --> evidence check --> hedge demotion   deterministic
                              v
   rule-based judge --> merge | merge with open questions |
                        another round (up to 3) | manual review
```

- Both agents read the same transcript. Neither sees the other's reply
  within a round; each round's critiques feed the next.
- The guardrails turn unproven or hedged blockers into questions, and
  the judge derives each agent's verdict from what is left.
- A malformed reply, a timeout, or input too large for the model ends
  in manual review, never approval.
- Every run writes a JSON decision record with input hashes, prompt and
  judge versions, the retrieved context and per-call token telemetry,
  so any decision can be traced.

More: [design and key decisions](docs/design.md).

## Results

On the bridge fixture, a refactor of Havne's Qt bridge (the fixtures'
revisions use its earlier name, `QtTune`):

| Stage | Valid blockers |
|---|---|
| First real run (one debate) | 2 of 12 (17%) |
| Layer rules and a hedge guardrail (one debate) | 4 of 6 (67%) |
| Blockers must quote post-change code (10 samples) | 17 of 18 (94%) |
| Shipped: code fenced as data, claim-quote linkage (19 samples) | 30 of 32 (94%), 0.11 false positives per review |

On a corpus of seven other real Havne diffs (66 samples), 64% of stored
blockers are valid, with a mean recall of 0.41 per known bug. The quote
rule costs recall where a bug is a deleted safety check, and one
false-positive class has resisted every lever tried. Both are written
up with the attempts that failed: [full results](docs/results.md), and
the measurement log in
[ADR-0002](docs/decisions/0002-adjudication-and-fp-remediation.md).

## Where to look

| To see | Look at |
|---|---|
| The judge and guardrails: pure, deterministic, unit-tested | [adjudication.py](adjudication.py) |
| The debate protocol and the decision records | [debate.py](debate.py) |
| Testing an LLM system without a model | [tests/](tests/) |
| What was measured, what shipped, what did not | [docs/results.md](docs/results.md) |
| How decisions were made, predictions included | [docs/decisions/](docs/decisions/) |
| Current state, limitations and backlog | [STATUS.md](STATUS.md) |
| Every file and its purpose | [docs/file-map.md](docs/file-map.md) |

## Quick start

```sh
pip install -r requirements.txt
python -m unittest discover -s tests      # no model needed

# with Ollama running and the models from config.py pulled:
python orchestrator.py --proposal "Describe the change" --diff path/to/change.diff
```

Every command, including the evaluation harness: [usage](docs/usage.md).

## Limitations

- Precision drops off the first fixture: 94% of stored blockers are
  valid there, 64% on the corpus.
- Small local models are slow: an accepted reviewer reply takes a median
  of 83 s on a 12 GB GPU, and diffs above about 30K characters are
  refused, not truncated.
- A quote proves that code exists, not that it supports the claim, so
  some confident wrong claims still get through.

## Links

- [Havne](https://github.com/erickramer42/havne)
- [Ollama](https://ollama.com)
- [Adapting the tribunal to another codebase](docs/portability_guide.md)

## License

MIT; see [LICENSE](LICENSE).
