# Multi-Agent Code Review Tribunal

Two local LLMs review a code change, and deterministic Python decides
whether it can merge. I built it, without an agent framework, to review
[QtTune](https://github.com/erickramer42/qttune), my C/C++/Qt ECU-tuning
application. I measured it on real diffs, wrote my predictions down
before each run, and published the failures next to the fixes.

## Highlights

- **A real workload on local models.** Two models served by Ollama on
  one 12 GB GPU debate real QtTune diffs: a code reviewer
  (laguna-xs-2.1) and a domain engineer (gemma4:12b). There is no
  LangChain or AutoGen; the orchestration is plain Python.
- **The model never makes the decision.**
  - Verdicts are derived from what the agents wrote, never from the
    verdict they report.
  - A blocker must quote the code that shows the problem, and the quote
    is checked against the diff. Unverifiable or hedged claims become
    questions.
  - Every failure ends in manual review, never approval: a malformed
    reply, a timeout, empty input, or input too large for the model.
- **Measured and fixed, failure class by failure class.** On its first
  real diff, 2 of 12 blockers were correct. After the fixes, 80–94% of
  the reviewer's blockers are valid over 10-sample measurements.
- **It found real bugs.** The test diff turned out to recreate an older
  state of QtTune. From the diff alone, the reviewer found two bugs that
  had shipped there and were fixed later: a data race on a frame
  counter, and a frame freeze past 10,000 frames.
- **Built to be trusted.**
  - 161 regression tests run with no model, by faking Ollama at the
    HTTP layer, in CI on Python 3.11 and 3.13.
  - Prompts and judge rules are versioned and stamped into every
    decision record.
  - Each design change has an architecture decision record with its
    predictions.

## How it works

```
 diff + context ──► transcript: code fenced as data, layer rules,
                    facts retrieved from an index of the repo
                              │
              ┌───────────────┴───────────────┐
        code reviewer                   domain engineer     local LLMs,
              └───────────────┬───────────────┘             same transcript
                              ▼
   schema validation ─► evidence check ─► hedge demotion    deterministic
                              ▼
   rule-based judge ─► merge │ merge with open questions │
                       another round (up to 3) │ manual review
```

- **Both agents read the same transcript.** Neither sees the other's
  reply within a round, and each round's critiques are fed back for the
  next.
- **Guardrails, then a judge.** The guardrails turn unproven blockers
  into questions. The judge then derives each agent's verdict from what
  is left.
- **Every run writes a JSON decision record.** It holds input hashes,
  prompt and judge versions, the retrieved context and per-call token
  telemetry, so any decision can be traced and re-run.

More: [design and key decisions](docs/design.md).

## Results

All on the same real diff, a 300-line refactor of QtTune's Qt bridge:

| Stage | Correct blockers |
|---|---|
| First real run (one debate, 3 rounds) | 2 of 12 (17%) |
| Layer rules and a hedge guardrail (one debate, 3 rounds) | 4 of 6 (67%), one bug stated four times |
| Facts retrieved from a repo index (round 1, 3 runs) | 3 of 10 (30%) |
| Blockers must quote post-change code (round 1, 10 samples) | 17 of 18 (94%) |
| Reviewed code fenced as data, current (round 1, 10 samples) | 20 of 25 (80%); the data race found in 10 of 10 runs |

The early rows were re-labelled against the code the diff leaves; the
first labels had used the current QtTune tree. That turned the data-race
blockers from false positives into true ones, and the first run's only
"true positive" into a false one, a bug in code the diff removes.
The table only shows the wins. The same measurements recorded a new
class of false positives, a run that ran out of context, and a true
claim demoted for hedging. They are all published, with the fixes:
[full results](docs/results.md), and the complete measurement log in
[ADR-0002](docs/decisions/0002-adjudication-and-fp-remediation.md).

## Where to look

| To see | Look at |
|---|---|
| The judge and guardrails: pure, deterministic, unit-tested | [adjudication.py](adjudication.py) |
| The debate protocol and the decision records | [debate.py](debate.py) |
| Testing an LLM system without a model | [tests/](tests/) |
| How decisions were made and measured | [docs/decisions/](docs/decisions/) |
| Current state, known limitations and backlog | [STATUS.md](STATUS.md) |

## Quick start

```sh
pip install -r requirements.txt
python -m unittest discover -s tests      # no model needed

# with Ollama running and the models from config.py pulled:
python orchestrator.py --proposal "Describe the change" --diff path/to/change.diff
```

Every command, including the eval harness: [usage](docs/usage.md).

## Limitations

- **Precision drops off the first fixture.** On a corpus of seven real
  diffs, 57% of blockers were valid, against 80–94% on the fixture the
  guardrails were tuned on, and the quote rule cost recall on bugs that
  remove a safety check.
- **Small local models are slow.** A reviewer call takes 1–4 minutes.
  At the current context window, diffs above about 30K characters are
  refused, not truncated.
- **A quote proves that code exists, not that it supports the claim.**
  Some confident wrong claims still get through.

## Links

- [QtTune](https://github.com/erickramer42/qttune)
- [Ollama](https://ollama.com)
- [Adapting the tribunal to another codebase](docs/portability_guide.md)
