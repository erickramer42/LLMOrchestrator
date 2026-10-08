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
NUM_CTX = 16384            # Validated by fp_rate_probe (5/5 clean)
REQUEST_TIMEOUT_S = 600    # Kept at 600s per probe latency discussion
TEMPERATURE_EXPLORATION = 0.7
TEMPERATURE_RETRY = 0.05

# ============ PROMPT COMPOSITION ============
REVIEWER_IMPL_PROMPT = REVIEWER_SYSTEM + IMPL_SCOPE_CLAUSE
REVIEWER_HEADER_PROMPT = REVIEWER_SYSTEM + HEADER_SCOPE_CLAUSE
