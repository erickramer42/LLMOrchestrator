# Multi-Agent Code Review Tribunal

Two local LLMs review a code change, and deterministic Python decides
whether it can merge. I built it, without an agent framework, to review
[QtTune](https://github.com/erickramer42/qttune), my C/C++/Qt ECU-tuning
application, and measured it on real diffs: every prediction is written
down before its run, and the failures are published next to the fixes.

## Highlights

- **A real workload on local models.** Two models served by Ollama on
  one 12 GB GPU review real QtTune diffs: a code reviewer
  (laguna-xs-2.1) and a domain engineer (gemma4:12b). No LangChain or
  AutoGen; the orchestration is plain Python.
- **The model never makes the decision.**
  - Verdicts are derived from what the agents wrote, never from the
    verdict they report.
  - A blocker must quote the code that shows the problem, and the quote
    is checked against the diff. Unverifiable or hedged claims become
    questions.
  - Every failure ends in manual review, never approval: a malformed
    reply, a timeout, empty input, or input too large for the model.
- **From 17% to 94%.** On its first real diff, 2 of 12 blockers were
  correct. After fixes made one failure class at a time, 94% of the
  reviewer's stored blockers on that diff are valid.
- **It found real bugs.** The test diff recreates an older state of
  QtTune. From the diff alone, the reviewer found two bugs that had
  shipped there and were fixed later: a data race on a frame counter,
  and a frame freeze past 10,000 frames.
- **Measured like an experiment.** Twenty-one measurements so far.
  From the first re-measurement on, each change's prediction and ship
  rule were written before its first sample; hand labels come before
  scoring, and no-model ceiling checks and pilots come before GPU time.
  Eight candidate changes failed their rules and are published with the
  reasons.
- **Built to be trusted.** Over 200 regression tests run with no model
  by faking Ollama at the HTTP layer, in CI on Python 3.11 and 3.13.
  Prompts and judge rules are versioned and stamped into every decision
  record.

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
  reply within a round; each round's critiques are fed into the next.
- **Guardrails, then a judge.** The guardrails turn unproven blockers
  into questions; the judge derives each agent's verdict from what is
  left.
- **Every run writes a JSON decision record** with input hashes, prompt
  and judge versions, the retrieved context and per-call token
  telemetry, so any decision can be traced and re-run.

More: [design and key decisions](docs/design.md).

## Results

On the bridge fixture, a 300-line refactor of QtTune's Qt bridge:

| Stage | Valid blockers |
|---|---|
| First real run (one debate) | 2 of 12 (17%) |
| Layer rules and a hedge guardrail (one debate) | 4 of 6 (67%) |
| Blockers must quote post-change code (10 samples) | 17 of 18 (94%) |
| Current: code fenced as data, claim–quote linkage (19 samples) | 30 of 32 (94%), 0.11 false positives per review |

On a corpus of seven other real QtTune diffs, the same system keeps
64% of its stored blockers valid, with a mean recall of 0.41 per known
bug. The quote rule that fixed the first diff costs recall when a bug
is a deleted safety check, and one false-positive class has resisted
every lever tried so far. Both are documented with the attempts that
failed: [full results](docs/results.md), and the complete measurement
log in [ADR-0002](docs/decisions/0002-adjudication-and-fp-remediation.md).

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

- **Precision drops off the first fixture:** 94% valid there, 64% on
  the corpus.
- **Small local models are slow.** A reviewer call takes 1–4 minutes;
  diffs above about 30K characters are refused, not truncated.
- **A quote proves that code exists, not that it supports the claim.**
  Some confident wrong claims still get through.

## Links

- [QtTune](https://github.com/erickramer42/qttune)
- [Ollama](https://ollama.com)
- [Adapting the tribunal to another codebase](docs/portability_guide.md)
