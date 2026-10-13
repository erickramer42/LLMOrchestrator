"""Ollama client — single agent turn with JSON-mode enforcement and retries.
The only module that talks to the network."""

import copy
import json
import time
from typing import Callable, Optional, Tuple

import requests

from config import NUM_CTX, OLLAMA_BASE_URL, REQUEST_TIMEOUT_S, TEMPERATURE_RETRY
from reviewer_prompt import FAILURE_SENTINEL

MAX_ATTEMPTS = 3
RETRY_BACKOFF_S = 5

# validate(parsed) -> (normalized, None) or (None, reason)
Validator = Callable[[object], Tuple[Optional[dict], Optional[str]]]


def failure_result(reason: str) -> dict:
    """Fresh fail-closed sentinel. Deep copy so callers never share (and
    can never mutate) the module-level sentinel's lists."""
    out = copy.deepcopy(FAILURE_SENTINEL)
    out["failure_reason"] = reason
    return out


def call_agent(model: str, system_prompt: str, transcript: str,
               temperature: float, validate: Optional[Validator] = None) -> dict:
    """Single agent turn with JSON-mode enforcement and retry logic.

    validate, when given, checks the parsed reply against the caller's
    schema (see adjudication.normalize_agent_output). A reply that fails
    it is retried with a corrective message, exactly like invalid JSON.
    Returns a failure sentinel carrying 'failure_reason' when every
    attempt fails (fail closed)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript},
    ]
    reason = "no attempts made"

    for attempt in range(MAX_ATTEMPTS):
        last = attempt == MAX_ATTEMPTS - 1
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature if attempt == 0 else TEMPERATURE_RETRY,
                "num_ctx": NUM_CTX,
            },
        }

        # ---- transport ----
        try:
            resp = requests.post(OLLAMA_BASE_URL, json=payload,
                                 timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            body = resp.json()
            content = body["message"]["content"]
        except requests.exceptions.Timeout:
            reason = f"timeout after {REQUEST_TIMEOUT_S}s"
        except requests.exceptions.RequestException as e:
            detail = ""
            if getattr(e, "response", None) is not None:
                detail = f" {e.response.text[:200]}"
            reason = f"request failed: {type(e).__name__}{detail}"
        except (KeyError, TypeError, ValueError) as e:
            reason = f"malformed Ollama response: {type(e).__name__}: {e}"
        else:
            # ---- content ----
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                reason = "reply was not valid JSON"
                if body.get("done_reason") == "length":
                    reason += (" (done_reason=length: output truncated; "
                               "check NUM_CTX)")
                messages.append({"role": "user",
                                 "content": "Invalid JSON. Reply with valid JSON only."})
                print(f"    ({model} attempt {attempt}: {reason})")
                continue
            if validate is None:
                return parsed
            normalized, problem = validate(parsed)
            if problem is None:
                return normalized
            reason = f"schema violation: {problem}"
            messages.append({"role": "user", "content": (
                f"Invalid reply: {problem}. Reply with valid JSON only, "
                "using exactly the keys from your instructions.")})
            print(f"    ({model} attempt {attempt}: {reason})")
            continue

        print(f"    ({model} attempt {attempt}: {reason}"
              f"{'' if last else ', retrying'})")
        if not last:
            time.sleep(RETRY_BACKOFF_S)

    return failure_result(reason)
