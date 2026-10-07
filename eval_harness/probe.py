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

def call(model: str, code: str) -> dict:
    system = REVIEWER_SYSTEM + HEADER_SCOPE_CLAUSE
    r = None
    for attempt in range(3):
        payload = {"model": model, "stream": False, "format": "json",
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": code}],
                   "options": {"temperature": 0.2 if attempt == 0 else 0.05,
                               "num_ctx": 16384}}
        try:
            resp = requests.post(OLLAMA, json=payload, timeout=600)
            r = resp.json()
            return json.loads(r["message"]["content"])
        except json.JSONDecodeError:
            raw = r.get("message", {}).get("content", "") if r else ""
            meta = {k: r.get(k) for k in ("done_reason", "eval_count", "total_duration")} if r else {}
            print(f"    (parse fail attempt {attempt}: content={raw[:60]!r} meta={meta})")
    return {"verdict": "PARSE_FAILURE", "blockers": [], "questions": [], "nits": []}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="False-positive rate probe")
    parser.add_argument("--model", type=str, default=MODEL_DEFAULT,
                        help="Model to test")
    parser.add_argument("--fixture", type=str,
                        help="Path to fixture file (default: core.h)")
    parser.add_argument("--runs", type=int, default=RUNS_DEFAULT,
                        help="Number of probe runs")
    args = parser.parse_args()

    MODEL = args.model
    RUNS = args.runs
    
    # Use provided path or default to QtTune's core.h
    if args.fixture and Path(args.fixture).exists():
        CORE_HEADER_PATH = Path(args.fixture)
    else:
        CORE_HEADER_PATH = Path("core/include/qttune/core.h")

    code = CORE_HEADER_PATH.read_text()
    print(f"Fixture: {CORE_HEADER_PATH.resolve()}")
    print(f"Model: {MODEL} | Prompt: {PROMPT_VERSION} | Runs: {RUNS}\n")

    results = []
    for i in range(RUNS):
        out = call(MODEL, code)
        verdict = out.get("verdict", "?")
        blockers = out.get("blockers", [])
        questions = out.get("questions", [])
        inflated = verdict == "reject" and not blockers
        timed_out = verdict == "TIMEOUT"
        results.append({"verdict": verdict, "blockers": blockers,
                        "questions": questions, "inflated": inflated,
                        "timed_out": timed_out})
        tag = "TIMEOUT" if timed_out else ("INFLATED" if inflated else verdict.upper())
        print(f"  run {i+1}: {tag:10} blockers={len(blockers)} "
              f"questions={len(questions)}")
        for b in blockers:
            print(f"          BLOCKER: {b}")

    fp_runs = sum(1 for r_ in results if r_["blockers"])
    inflated_runs = sum(1 for r_ in results if r_["inflated"])
    timeout_runs = sum(1 for r_ in results if r_["timed_out"])
    parse_fails = sum(1 for r_ in results if r_["verdict"] == "PARSE_FAILURE")

    print(f"\nBlocker-FP rate on scoped header review: {fp_runs}/{RUNS}")
    print(f"Verdict inflation (reject w/o blockers):  {inflated_runs}/{RUNS}")
    print(f"Timeouts:                                 {timeout_runs}/{RUNS}")
    print(f"Parse failures:                           {parse_fails}/{RUNS}")

    if fp_runs == 0 and inflated_runs == 0 and timeout_runs == 0:
        print("=> CLEAN: model viable for reviewer seat with scoped prompt")
    elif fp_runs <= 1 and inflated_runs <= 1 and timeout_runs <= 1:
        print("=> BORDERLINE: residual noise; consider prompt iteration")
    else:
        print("=> SYSTEMATIC: disqualifies model; alternative needed")

    record = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "prompt_version": PROMPT_VERSION, "model": MODEL,
              "runs": RUNS, "fixture": str(CORE_HEADER_PATH.resolve()),
              "results": results,
              "summary": {"blocker_fp_runs": fp_runs, "inflated_runs": inflated_runs,
                          "timeout_runs": timeout_runs,
                          "parse_fails": parse_fails}}
    out_file = Path("probe_logs") / f"fp_{MODEL.replace(':','_')}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(record, indent=2))
    print(f"\nSaved: {out_file}")
    