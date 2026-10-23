"""raw_call.py — the probe's and the bake-off's model call.

One raw Ollama request per attempt, with the settings both scripts were
measured with (ADR-0001, probe_logs/): num_ctx 16384, no output cap,
temperature 0.2 on the first attempt and 0.05 on the two retries, a
600s timeout, and no corrective message between attempts. It does not
use agent_client or config, so changing the debate's settings leaves
these numbers comparable with the recorded ones."""

import json
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
