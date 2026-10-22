"""Central configuration — models, runtime parameters, prompt composition.
Single place to swap models or tune knobs; nothing else hardcodes these."""

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
# Output cap per attempt, thinking included. Runaways are loops (ADR-0002),
# so the cap makes them fail early and the retry recovers. It sits above
# every finished reply seen so far (longest 10,097 tokens).
NUM_PREDICT = 12288
REQUEST_TIMEOUT_S = 600    # Kept at 600s per probe latency discussion
TEMPERATURE_EXPLORATION = 0.7
TEMPERATURE_RETRY = 0.05

# ============ PROMPT COMPOSITION ============
REVIEWER_IMPL_PROMPT = REVIEWER_SYSTEM + IMPL_SCOPE_CLAUSE
REVIEWER_HEADER_PROMPT = REVIEWER_SYSTEM + HEADER_SCOPE_CLAUSE
