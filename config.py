"""Central configuration — models, runtime parameters, prompt composition.
Single place to swap models or tune knobs for debates, the measurements,
the golden suite and the indexer. The probe and the bake-off keep the
settings they were measured with, in eval_harness/raw_call.py, so their
numbers stay comparable with ADR-0001's."""

from reviewer_prompt import (REVIEWER_SYSTEM, IMPL_SCOPE_CLAUSE,
                             HEADER_SCOPE_CLAUSE)

# ============ RUNTIME ============
OLLAMA_BASE_URL = "http://localhost:11434/api/chat"

MODELS = {
    "code_reviewer": "laguna-xs-2.1",
    "auto_engineer": "gemma4:12b",
}

MAX_DEBATE_ROUNDS = 3
# 24576 (was 16384, which the probe validated on header-only fixtures). On
# the bridge diff the prompt alone is ~9.4K tokens, and finished reviewer
# replies reach 10K output tokens, thinking included. Runaway thinking
# fills any window; that is backlog #16, not a reason to grow this
# (ADR-0002, 2026-10-22 follow-ups).
NUM_CTX = 24576
# Output cap per attempt, thinking included. A runaway (mostly a search that
# keeps reopening its conclusion, rarely a loop; ADR-0002, "Runaway
# Diagnostic") stops here and the retry recovers. Accepted replies run up
# to the cap (longest 12,248 tokens), so it is not lowered.
NUM_PREDICT = 12288
# Input check (judge j7): a round-1 request is estimated at one token per
# this many chars, and refused above NUM_CTX - NUM_PREDICT tokens, so every
# reply has its full output cap and Ollama never has to cut the prompt.
# Below every ratio on record (2026-10-23, bridge fixture): laguna-xs-2.1
# 3.43-3.52 chars per token, gemma4:12b 3.21-3.30. At 24576 / 12288 the
# limit is 36,864 chars. The bridge fixture's request is ~33.3K chars, so
# with its prompt, pack and proposal a diff above ~30K chars is refused.
CHARS_PER_TOKEN_FLOOR = 3.0
REQUEST_TIMEOUT_S = 600    # Kept at 600s per probe latency discussion
TEMPERATURE_EXPLORATION = 0.7
TEMPERATURE_RETRY = 0.05

# ============ PROMPT COMPOSITION ============
REVIEWER_IMPL_PROMPT = REVIEWER_SYSTEM + IMPL_SCOPE_CLAUSE
REVIEWER_HEADER_PROMPT = REVIEWER_SYSTEM + HEADER_SCOPE_CLAUSE
