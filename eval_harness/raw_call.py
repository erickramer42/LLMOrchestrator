"""The probe's and the bake-off's model call.

One raw Ollama request per attempt, with the settings both scripts were
measured with (ADR-0001, probe_logs/): num_ctx 16384, no output cap,
temperature 0.2 on the first attempt and 0.05 on the two retries, a
600s timeout, and no corrective message between attempts. It does not
use agent_client or config, so changing the debate's settings leaves
these numbers comparable with the recorded ones."""

import json
import time
from typing import Optional, Tuple

import requests

OLLAMA = "http://localhost:11434/api/chat"
ATTEMPTS = 3
NUM_CTX = 16384
TIMEOUT_S = 600


def review(model: str, system: str, code: str) -> Tuple[dict, Optional[str], str]:
    """(reply, failure, reason) for one review of code. failure is None
    when an attempt returned a JSON object; 'timeout' when a request timed
    out, which is not retried (the probe measures the timeout rate); else
    'parse': no attempt returned a JSON object. reason says why the last
    attempt failed, with Ollama's own message for an HTTP error."""
    r = None
    reason = "no attempts made"
    for attempt in range(ATTEMPTS):
        payload = {"model": model, "stream": False, "format": "json",
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": code}],
                   "options": {"temperature": 0.2 if attempt == 0 else 0.05,
                               "num_ctx": NUM_CTX}}
        try:
            resp = requests.post(OLLAMA, json=payload, timeout=TIMEOUT_S)
            resp.raise_for_status()
            r = resp.json()
            out = json.loads(r["message"]["content"])
            if isinstance(out, dict):
                return out, None, ""
            reason = f"reply is a JSON {type(out).__name__}, expected an object"
        except requests.exceptions.Timeout:
            return {}, "timeout", f"timeout after {TIMEOUT_S}s"
        except requests.exceptions.RequestException as e:
            detail = ""
            if getattr(e, "response", None) is not None:
                detail = f" {e.response.text[:200]}"
            reason = f"request failed: {type(e).__name__}{detail}"
        except json.JSONDecodeError:
            raw = r.get("message", {}).get("content", "") if r else ""
            meta = {k: r.get(k) for k in ("done_reason", "eval_count", "total_duration")} if r else {}
            reason = "reply was not valid JSON"
            print(f"    (parse fail attempt {attempt}: content={raw[:60]!r} meta={meta})")
        except (KeyError, TypeError) as e:
            reason = f"malformed Ollama response: {type(e).__name__}"
    return {}, "parse", reason


# The twenty-sixth measurement's call (ADR-0002): prose or JSON, one attempt
CHAT_OPTIONS = {"num_ctx": 24576, "num_predict": 12288, "temperature": 0.7}
CHAT_TIMEOUT_S = 1800


def chat(model: str, system: str, user: str, json_mode: bool) -> Tuple[str, dict]:
    """(reply text, call info) for one request with CHAT_OPTIONS and no
    retry. info holds Ollama's done_reason and token counts, the thinking's
    length, the wall time, and error: None, or why no reply came."""
    payload = {"model": model, "stream": False,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "options": dict(CHAT_OPTIONS)}
    if json_mode:
        payload["format"] = "json"
    info = {"error": None, "done_reason": None, "prompt_eval_count": None,
            "eval_count": None, "thinking_chars": 0, "wall_s": None}
    started = time.monotonic()
    try:
        resp = requests.post(OLLAMA, json=payload, timeout=CHAT_TIMEOUT_S)
        resp.raise_for_status()
        body = resp.json()
        message = body["message"]
        reply = message.get("content") or ""
        if not isinstance(reply, str):
            raise TypeError("reply is not a string")
        info.update({k: body.get(k) for k in ("done_reason", "prompt_eval_count", "eval_count")},
                    thinking_chars=len(message.get("thinking") or ""))
    except requests.exceptions.Timeout:
        reply, info["error"] = "", f"timeout after {CHAT_TIMEOUT_S}s"
    except requests.exceptions.RequestException as e:
        detail = f" {e.response.text[:200]}" if getattr(e, "response", None) is not None else ""
        reply, info["error"] = "", f"request failed: {type(e).__name__}{detail}"
    except (KeyError, TypeError, ValueError) as e:
        reply, info["error"] = "", f"malformed Ollama response: {type(e).__name__}"
    info["wall_s"] = round(time.monotonic() - started, 1)
    return reply, info
