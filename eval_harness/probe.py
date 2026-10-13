#!/usr/bin/env python3
"""probe.py — false-positive probe with scoped prompts and
verdict-aware metrics. Outputs a timestamped JSON record with PROMPT_VERSION.
example usage:
    python -m eval_harness.probe --model laguna-xs-2.1 --fixture ../<your_project_path>/<filename_to_review>"""

import json, requests, argparse
from datetime import datetime, timezone
from pathlib import Path

from reviewer_prompt import (REVIEWER_SYSTEM, HEADER_SCOPE_CLAUSE,
                             PROMPT_VERSION)

OLLAMA = "http://localhost:11434/api/chat"
MODEL_DEFAULT = "laguna-xs-2.1"
RUNS_DEFAULT = 5
TIMEOUT_S = 600


def _failed(verdict: str, reason: str) -> dict:
    return {"verdict": verdict, "blockers": [], "questions": [], "nits": [],
            "failure_reason": reason}


def call(model: str, code: str) -> dict:
    """One probe run. Returns verdict TIMEOUT on a request timeout (not
    retried: the timeout rate is what this measures) and PARSE_FAILURE
    when no attempt yields a JSON object."""
    system = REVIEWER_SYSTEM + HEADER_SCOPE_CLAUSE
    r = None
    reason = "no attempts made"
    for attempt in range(3):
        payload = {"model": model, "stream": False, "format": "json",
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": code}],
                   "options": {"temperature": 0.2 if attempt == 0 else 0.05,
                               "num_ctx": 16384}}
        try:
            resp = requests.post(OLLAMA, json=payload, timeout=TIMEOUT_S)
            r = resp.json()
            out = json.loads(r["message"]["content"])
            if isinstance(out, dict):
                return out
            reason = f"reply is a JSON {type(out).__name__}, expected an object"
        except requests.exceptions.Timeout:
            return _failed("TIMEOUT", f"timeout after {TIMEOUT_S}s")
        except requests.exceptions.RequestException as e:
            reason = f"request failed: {type(e).__name__}"
        except json.JSONDecodeError:
            raw = r.get("message", {}).get("content", "") if r else ""
            meta = {k: r.get(k) for k in ("done_reason", "eval_count", "total_duration")} if r else {}
            reason = "reply was not valid JSON"
            print(f"    (parse fail attempt {attempt}: content={raw[:60]!r} meta={meta})")
        except (KeyError, TypeError) as e:
            reason = f"malformed Ollama response: {type(e).__name__}"
    return _failed("PARSE_FAILURE", reason)


def summarize(results: list) -> dict:
    """Aggregate run results and classify the model. Unusable runs
    (parse failures, timeouts) count against the model: a probe where
    nothing parsed must never read as CLEAN."""
    runs = len(results)
    s = {
        "blocker_fp_runs": sum(1 for r_ in results if r_["blockers"]),
        "inflated_runs": sum(1 for r_ in results if r_["inflated"]),
        "timeout_runs": sum(1 for r_ in results if r_["timed_out"]),
        "parse_fails": sum(1 for r_ in results if r_["verdict"] == "PARSE_FAILURE"),
    }
    noise = (s["blocker_fp_runs"], s["inflated_runs"], s["timeout_runs"],
             s["parse_fails"])
    if runs and s["timeout_runs"] + s["parse_fails"] == runs:
        s["classification"] = "NO_DATA"
    elif all(n == 0 for n in noise):
        s["classification"] = "CLEAN"
    elif all(n <= 1 for n in noise):
        s["classification"] = "BORDERLINE"
    else:
        s["classification"] = "SYSTEMATIC"
    return s


VERDICT_TEXT = {
    "NO_DATA": "=> NO DATA: every run timed out or failed to parse; fix the "
               "model/server setup before judging the model",
    "CLEAN": "=> CLEAN: model viable for reviewer seat with scoped prompt",
    "BORDERLINE": "=> BORDERLINE: residual noise; consider prompt iteration",
    "SYSTEMATIC": "=> SYSTEMATIC: disqualifies model; alternative needed",
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="False-positive rate probe")
    parser.add_argument("--model", type=str, default=MODEL_DEFAULT,
                        help="Model to test")
    parser.add_argument("--fixture", type=str, required=True,
                        help="Path to a clean fixture file, e.g. "
                             "../qttune/core/include/qttune/core.h")
    parser.add_argument("--runs", type=int, default=RUNS_DEFAULT,
                        help="Number of probe runs")
    args = parser.parse_args()

    MODEL = args.model
    RUNS = args.runs

    CORE_HEADER_PATH = Path(args.fixture)
    if not CORE_HEADER_PATH.is_file():
        raise SystemExit(f"ERROR: --fixture not found: {args.fixture}")

    code = CORE_HEADER_PATH.read_text(encoding="utf-8", errors="replace")
    print(f"Fixture: {CORE_HEADER_PATH.resolve()}")
    print(f"Model: {MODEL} | Prompt: {PROMPT_VERSION} | Runs: {RUNS}\n")

    results = []
    for i in range(RUNS):
        out = call(MODEL, code)
        verdict = str(out.get("verdict", "?"))
        blockers = out.get("blockers", []) or []
        questions = out.get("questions", []) or []
        inflated = verdict == "reject" and not blockers
        timed_out = verdict == "TIMEOUT"
        results.append({"verdict": verdict, "blockers": blockers,
                        "questions": questions, "inflated": inflated,
                        "timed_out": timed_out,
                        "failure_reason": out.get("failure_reason")})
        tag = "TIMEOUT" if timed_out else ("INFLATED" if inflated else verdict.upper())
        print(f"  run {i+1}: {tag:10} blockers={len(blockers)} "
              f"questions={len(questions)}")
        for b in blockers:
            print(f"          BLOCKER: {b}")

    summary = summarize(results)
    print(f"\nBlocker-FP rate on scoped header review: {summary['blocker_fp_runs']}/{RUNS}")
    print(f"Verdict inflation (reject w/o blockers):  {summary['inflated_runs']}/{RUNS}")
    print(f"Timeouts:                                 {summary['timeout_runs']}/{RUNS}")
    print(f"Parse failures:                           {summary['parse_fails']}/{RUNS}")
    print(VERDICT_TEXT[summary["classification"]])

    record = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "prompt_version": PROMPT_VERSION, "model": MODEL,
              "runs": RUNS, "fixture": str(CORE_HEADER_PATH.resolve()),
              "results": results,
              "summary": summary}
    out_file = Path("probe_logs") / f"fp_{MODEL.replace(':','_')}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_file}")
