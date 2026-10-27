"""Ollama client — single agent turn with JSON-mode enforcement and retries.
The only module that talks to the network. Retry notes go to the
'agent_client' logger as warnings; with no logging configured, Python
prints them to stderr."""

import copy
import json
import logging
import time
from typing import Callable, List, Optional, Tuple

import requests

from config import (NUM_CTX, NUM_PREDICT, OLLAMA_BASE_URL, REQUEST_TIMEOUT_S,
                    TEMPERATURE_RETRY)

log = logging.getLogger(__name__)

# What a call returns when every attempt failed. Its verdict fails closed
# in the judge (adjudication.derive_verdict) and in every scorer.
FAILURE_SENTINEL = {"verdict": "PARSE_FAILURE", "blockers": [],
                    "concerns": [], "questions": []}

MAX_ATTEMPTS = 3
RETRY_BACKOFF_S = 5
FAILURE_TAIL_CHARS = 400  # how much of a failed reply telemetry keeps
# An attempt that runs this long, or to the cap, keeps its whole thinking:
# the material for telling a loop from a long search (backlog #19). About
# one accepted reviewer reply in ten runs this long.
LONG_THINKING_TOKENS = 8192

# What the next attempt is told after an unusable reply. A schema
# violation's failure reason is SCHEMA_PREFIX plus the problem.
JSON_CORRECTION = "Invalid JSON. Reply with valid JSON only."
SCHEMA_PREFIX = "schema violation: "


def schema_correction(problem: str) -> str:
    return (f"Invalid reply: {problem}. Reply with valid JSON only, "
            "using exactly the keys from your instructions.")


# validate(parsed) -> (normalized, None) or (None, reason)
Validator = Callable[[object], Tuple[Optional[dict], Optional[str]]]


def failure_result(reason: str) -> dict:
    """Fresh fail-closed sentinel. Deep copy so callers never share (and
    can never mutate) the module-level sentinel's lists."""
    out = copy.deepcopy(FAILURE_SENTINEL)
    out["failure_reason"] = reason
    return out


def _attempt_stats(attempt: int, temperature: float, prompt_chars: int,
                   started: float, body: dict, reason: Optional[str]) -> dict:
    """One telemetry entry. Token counts and done_reason are Ollama's own,
    None when no reply arrived. A prompt_eval_count near NUM_CTX means the
    prompt is crowding the window; a large eval_count with
    done_reason=length means the output (thinking included) ran out.
    Ollama may count fewer prompt tokens when it reuses a cached prefix,
    so prompt_chars is recorded as a deterministic size as well.

    eval_count includes the model's thinking, which Ollama returns apart
    from the reply. A failed attempt also keeps the tail of both, so a
    runaway shows whether the model was looping or still reasoning. An
    attempt that hit the cap or ran past LONG_THINKING_TOKENS, accepted or
    not, keeps its whole thinking as well."""
    message = body.get("message")
    message = message if isinstance(message, dict) else {}
    thinking = message.get("thinking")
    thinking = thinking if isinstance(thinking, str) else ""
    content = message.get("content")
    content = content if isinstance(content, str) else ""
    stats = {
        "attempt": attempt,
        "temperature": temperature,
        "prompt_chars": prompt_chars,
        "prompt_eval_count": body.get("prompt_eval_count"),
        "eval_count": body.get("eval_count"),
        "thinking_chars": len(thinking),
        "content_chars": len(content),
        "done_reason": body.get("done_reason"),
        "wall_s": round(time.monotonic() - started, 2),
        "outcome": reason or "ok",
    }
    if reason and (thinking or content):
        stats["thinking_tail"] = thinking[-FAILURE_TAIL_CHARS:]
        stats["content_tail"] = content[-FAILURE_TAIL_CHARS:]
    elif not reason:
        # The accepted reply verbatim (v12): records keep what the model
        # said, not only what normalization made of it. Thinking is not
        # kept, unless the attempt ran long (below).
        stats["reply"] = content
    eval_count = body.get("eval_count")
    if thinking and (body.get("done_reason") == "length" or (
            isinstance(eval_count, int) and eval_count >= LONG_THINKING_TOKENS)):
        stats["thinking"] = thinking
    return stats


def call_agent(model: str, system_prompt: str, transcript: str,
               temperature: float, validate: Optional[Validator] = None,
               telemetry: Optional[List[dict]] = None) -> dict:
    """Single agent turn with JSON-mode enforcement and retry logic.

    validate, when given, checks the parsed reply against the caller's
    schema (see adjudication.normalize_agent_output). A reply that fails
    it is retried with a corrective message, exactly like invalid JSON.
    Returns a failure sentinel carrying 'failure_reason' when every
    attempt fails (fail closed).

    telemetry, when given, receives one _attempt_stats entry per attempt,
    successful or not."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript},
    ]
    reason = "no attempts made"

    for attempt in range(MAX_ATTEMPTS):
        last = attempt == MAX_ATTEMPTS - 1
        attempt_temp = temperature if attempt == 0 else TEMPERATURE_RETRY
        body, result, reason, correction, stats = send_once(
            model, messages, attempt_temp, validate, attempt)
        if telemetry is not None:
            telemetry.append(stats)
        if reason is None:
            return result
        if correction:
            # The model replied, but unusably: say why and retry at once.
            messages.append({"role": "user", "content": correction})
            log.warning("    (%s attempt %d: %s)", model, attempt, reason)
            continue

        log.warning("    (%s attempt %d: %s%s)", model, attempt, reason,
                    "" if last else ", retrying")
        if not last:
            time.sleep(RETRY_BACKOFF_S)

    return failure_result(reason)


def send_once(model: str, messages: List[dict], temperature: float,
              validate: Optional[Validator] = None, attempt: int = 0
              ) -> Tuple[dict, Optional[dict], Optional[str], Optional[str], dict]:
    """One request exactly as call_agent sends it, without retries:
    (ollama_body, result, failure_reason, correction, telemetry entry).
    call_agent's attempts go through here; eval_harness.runaway re-sends a
    recorded attempt with it."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
        },
    }
    prompt_chars = sum(len(m["content"]) for m in messages)
    started = time.monotonic()
    body, result, reason, correction = _attempt(payload, validate)
    return (body, result, reason, correction,
            _attempt_stats(attempt, temperature, prompt_chars, started, body, reason))


def _attempt(payload: dict, validate: Optional[Validator]
             ) -> Tuple[dict, Optional[dict], Optional[str], Optional[str]]:
    """One request. Returns (ollama_body, result, failure_reason,
    correction). Exactly one of result and failure_reason is set.
    correction is the message for the model's next attempt when it replied
    with unusable content; it is None for transport failures."""
    body = {}
    # ---- transport ----
    try:
        resp = requests.post(OLLAMA_BASE_URL, json=payload,
                             timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        body = resp.json()
        content = body["message"]["content"]
        if not isinstance(content, str):
            raise TypeError(f"message.content is {type(content).__name__}, "
                            "expected a string")
    except requests.exceptions.Timeout:
        return {}, None, f"timeout after {REQUEST_TIMEOUT_S}s", None
    except requests.exceptions.RequestException as e:
        detail = ""
        if getattr(e, "response", None) is not None:
            detail = f" {e.response.text[:200]}"
        return {}, None, f"request failed: {type(e).__name__}{detail}", None
    except (KeyError, TypeError, ValueError) as e:
        return (body if isinstance(body, dict) else {}, None,
                f"malformed Ollama response: {type(e).__name__}: {e}", None)

    # ---- content ----
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        reason = "reply was not valid JSON"
        if body.get("done_reason") == "length":
            reason += (f" (done_reason=length: output truncated after "
                       f"{body.get('prompt_eval_count')} prompt + "
                       f"{body.get('eval_count')} output tokens; "
                       f"NUM_PREDICT={NUM_PREDICT}, check NUM_CTX={NUM_CTX})")
        return body, None, reason, JSON_CORRECTION
    if validate is None:
        return body, parsed, None, None
    normalized, problem = validate(parsed)
    if problem is None:
        return body, normalized, None, None
    return body, None, SCHEMA_PREFIX + problem, schema_correction(problem)
