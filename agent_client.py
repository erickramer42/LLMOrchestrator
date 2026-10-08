"""Ollama client — single agent turn with JSON-mode enforcement and retries.
The only module that talks to the network."""

import json
import time

import requests

from config import NUM_CTX, OLLAMA_BASE_URL, REQUEST_TIMEOUT_S, TEMPERATURE_RETRY
from reviewer_prompt import FAILURE_SENTINEL


def call_agent(model: str, system_prompt: str, transcript: str,
               temperature: float) -> dict:
    """Single agent turn with JSON-mode enforcement and retry logic.
    Returns FAILURE_SENTINEL on total failure (fail closed)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript},
    ]

    for attempt in range(3):
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
        try:
            resp = requests.post(OLLAMA_BASE_URL, json=payload,
                                 timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            result = resp.json()
            return json.loads(result["message"]["content"])
        except json.JSONDecodeError:
            messages.append({"role": "user",
                            "content": "Invalid JSON. Reply with valid JSON only."})
        except (requests.exceptions.Timeout,
                requests.exceptions.RequestException) as e:
            print(f"    ({model} attempt {attempt}: {type(e).__name__}, retrying)")
            time.sleep(5)

    return dict(FAILURE_SENTINEL)
