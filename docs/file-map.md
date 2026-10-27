# File Map

Every file in the repository and what it is for. For how the pieces fit
together, see [design.md](design.md); for the current versions, see
[STATUS.md](../STATUS.md).

## Review pipeline

| Path | Purpose |
|---|---|
| `orchestrator.py` | CLI entry point: argument parsing and dispatch only. `--golden`, `--proposal` and `--index` are mutually exclusive; `--proposal` needs `--diff` or `--context`. Inputs are read as UTF-8. |
| `config.py` | Models, `NUM_CTX`, the `NUM_PREDICT` output cap, the input check's chars-per-token floor, timeouts and temperatures; composes the reviewer prompts. The one place to swap models (the probe and bake-off excepted). |
| `agent_client.py` | The Ollama client and the only module that touches the network. One agent turn in JSON mode; invalid or schema-violating replies are retried with a corrective message, then fail closed with `FAILURE_SENTINEL`. Records per-attempt telemetry: token counts, thinking and reply sizes, `done_reason`, wall time, the verbatim accepted reply, the tails of failed ones, and the whole thinking of any attempt that hit the cap or ran past `LONG_THINKING_TOKENS` (backlog #19). |
| `adjudication.py` | Pure judging logic, no I/O: the verdict constants, schema validation (`normalize_agent_output`), the evidence check (`demote_unverified_blockers`: post-change quotes, and since j8 claim–quote linkage), the hedge check (`demote_hedged_blockers`), `derive_verdict`, `convergence_verdict` and `JUDGE_VERSION`. Imports cleanly in CI. |
| `debate.py` | The debate loop. Builds the transcript (fenced code, layer note, context pack, and from round 2 the CRITIQUES section), runs the input check, calls the agents, applies the guardrails, judges, and writes the decision record. Also the measurement modes: `run_round1_review` (a debate's first reviewer call alone) and `run_round2_pair` (two round-2 formats on the same round 1). The repair pass's helpers stay for `eval_harness/repair.py`; debates run with `REPAIR_PASS` off. |
| `diff_reader.py` | The one unified-diff reader: `read_diff`, `diff_paths`, `base_blobs`, and the identifier helpers (`IDENT`, `code_like`) the judge and retrieval share. Used by the evidence check, retrieval, its base check and layer mapping. |
| `reviewer_prompt.py` | The agents' system prompts and `PROMPT_VERSION`, with a comment per version on what changed and whether it shipped. |
| `file_metadata.py` | File path → layer (core, bridge, app, unknown), and the layer notes the transcript carries. |
| `golden_tests.py` | The golden suite: 3 live-model fixtures, reviewed through `debate.review_round1`, plus 7 deterministic hedge units taken from production blocker texts. |
| `review_fixtures.py` | The code snippets the golden suite and the bake-off share. Add a fixture rather than edit one. |

**Dependency direction (acyclic):** `reviewer_prompt`, `file_metadata`,
`diff_reader` and `review_fixtures` are leaves → `config` →
`agent_client` and `adjudication`, in parallel → `retrieval` → `debate`
→ `golden_tests` → `orchestrator`. `indexer` sits on `retrieval` and
`agent_client`, and only `orchestrator --index` imports it.
`eval_harness.common` sits on `retrieval`; `round1` and `round2` on
`common` and `debate`; `replay` on `common`, `adjudication` and
`diff_reader`. The probe and bake-off import only `reviewer_prompt`,
`eval_harness.raw_call` and `review_fixtures`. `tests/` sits on top.

## Repo context

| Path | Purpose |
|---|---|
| `indexer.py` | Offline indexer (`orchestrator.py --index <repo> [--no-llm]`): C typedefs, numeric constants, queued-connection call sites, and optional LLM purpose summaries cached in `repo_context_cache.json`. Records the source commit and each file's git blob id. |
| `retrieval.py` | Review-time retrieval (`build_context_pack`): purposes, types, constants and call sites tied to the diff, under a 6,000-character budget. Entries the diff removes are omitted and named; the base check compares the diff's pre-change blobs with the index. Holds `PACK_FORMAT_VERSION`. No model, no network. |
| `repo_context.json` | The committed index for QtTune, built from the bridge fixture's base (`e0c4c31`). Reviewing another diff needs an index of that diff's base (`--index-out`, `--index-file`). |

## Evaluation harness

| Path | Purpose |
|---|---|
| `eval_harness/common.py` | What the measurement scripts share: the `run`/`score` command line, the sample runner, record loading, attempt status, demoted-item recovery. |
| `eval_harness/round1.py` | Round-1 samples on any diff (`run`) and their scoring (`score`): blockers per run, symbol hits, and candidates for hand review; evidence-demoted items listed as `#e`, hedge-demoted as `#h`. |
| `eval_harness/round2.py` | The round-2 pair measurement: two round-2 formats on the same round-1 replies, compared on first-attempt pairs, with runaways counted per arm. |
| `eval_harness/corpus.py` | The real-diff corpus: `list` (sizes, layers, input and base checks; no model), `run` (round-1 samples with each fixture's own index, of the reviewer or, with `--engineer`, the engineer, either with another model) and `score` (recall per known bug, false-positive candidates, hand-label summary, call cost; engineer records apart). |
| `eval_harness/replay.py` | Offline replay, no model: re-judges archived replies under deterministic judge variants (gapped quotes, linkage, k-of-n voting, removed-line exceptions) and scores them with the hand labels; first checks that the current judge reproduces every stored split. `--corpus` does the same per corpus fixture. |
| `eval_harness/runaway.py` | Backlog #19, no model: measures how much a long reply's thinking repeats itself (k-word shingles seen earlier, prose and quoted code apart, by thirds), for telling a loop from a long search. |
| `eval_harness/repair.py` | The repair pass measured paired on archived replies (seventeenth measurement), its no-model ceiling check, and its successor's pilots (eighteenth). |
| `eval_harness/labels.json` | Hand labels for every bridge-fixture item scored since the tenth measurement (race, gate, deletion, removal objection, deleted test, other FP). |
| `eval_harness/corpus_labels.json` | Hand labels for every corpus item (known-bug ids and false-positive classes), each sample labeled before it was scored; a test pins each sample's counts. |
| `eval_harness/engineer_labels.json` | Hand labels for the engineer's corpus items (twenty-third measurement): every blocker, and each concern or question that states a known bug. |
| `eval_harness/probe.py`, `bakeoff.py`, `raw_call.py` | The false-positive probe and the model bake-off of ADR-0001, with the raw model call they were measured with (no `config.py` settings, no guardrails). |

## Fixtures and evidence

| Path | Purpose |
|---|---|
| `docs/fixtures/qttune_bridge_refactor.diff` | The bridge fixture: the reverse patch of QtTune `e0c4c31`. Its post-state is QtTune `8ffbf19`, which has two known bugs: the `m_currentFrameCount` race and the in-flight gate that freezes past 10,000 frames. |
| `docs/fixtures/qttune_core_e08b455.h` | QtTune's `core.h` at `e08b455`, the clean header behind the probe logs and header review 194320. |
| `docs/fixtures/corpus.json` | The corpus manifest: per fixture the commit, direction, base and post-state revisions, proposal, known bugs with their symbols, and what the removed lines leak. |
| `docs/fixtures/corpus/<id>/` | One corpus fixture: `change.diff` (tests, docs and `*.md` excluded) and the `--no-llm` index of its base. |
| `coach_artifacts/decision_debate_*.json` | Debate records: the 2026-10-07 baseline (`203917`), the v1 re-measurement (`014257`), the live-loop control (`170208`), the context-pack pilot and three scored runs (`201540`, `203802`, `204845`, `210548`), the header review (`194320`), and seven telemetry runs from 2026-10-22. |
| `coach_artifacts/measurement_round1_*.json` | Round-1 measurement records, one reviewer call each. The bridge fixture's are labeled in `labels.json`, the corpus's in `corpus_labels.json`; [history.md](history.md) and ADR-0002 give each sample's id range. Pilot records are kept but never scored. |
| `coach_artifacts/measurement_engineer_*.json` | Engineer measurement records, one engineer round-1 call each (`corpus run --engineer`), labeled in `engineer_labels.json`. |
| `coach_artifacts/measurement_round2_*.json` | Round-2 pair records from the eleventh and twelfth measurements. |
| `coach_artifacts/measurement_repair_*.json` | Repair-call records from the seventeenth and eighteenth measurements. |
| `coach_artifacts/measurement_runaway_*.json` | Re-sends of a recorded runaway attempt (`eval_harness.runaway repro`), from the runaway diagnostic; each keeps the attempt's telemetry, with its whole thinking when it ran long. |
| `probe_logs/fp_*.json` | The probe's 5-run aggregates (ADR-0001). |

## Tests, CI and docs

| Path | Purpose |
|---|---|
| `tests/test_deterministic.py` | The regression suite. Ollama is faked at the HTTP layer, so the real client, judge and debate code run without a model. Also pins the label counts of every scored sample. |
| `tests/test_retrieval.py` | Retrieval and indexer unit tests. |
| `.github/workflows/` | CI: compile check and the regression suite on Python 3.11 and 3.13, no Ollama. |
| `README.md` | The project in two minutes. |
| `STATUS.md` | Current state, work in progress, limitations, backlog and conventions. |
| `docs/design.md` | The pipeline and the design decisions behind it. |
| `docs/results.md` | What was measured, what shipped, and what did not. |
| `docs/usage.md` | Every command. |
| `docs/portability_guide.md` | Adapting the tribunal to another codebase. |
| `docs/history.md` | The dated engineering log. |
| `docs/decisions/` | ADR-0001 (model selection) and ADR-0002 (adjudication and every measurement, predictions included). |
