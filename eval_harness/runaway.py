"""runaway.py — does a long reply repeat itself? (backlog #19)

Reads the whole thinking that agent_client keeps for attempts that hit the
output cap or ran past LONG_THINKING_TOKENS, and measures repetition the
way an abort rule would have to see it: k-word shingles that already
occurred earlier in the same thinking. Code quoted in ``` fences (mostly
the diff, copied back) is counted apart from the model's own prose, since
re-quoting the input and restating its own reasoning are different loops.

    python -m eval_harness.runaway "coach_artifacts/measurement_round1_*.json"

No model is called. The repro subcommand re-sends one recorded round-1
attempt (system prompt, transcript and the corrections before it, at its
recorded temperature) after checking its size against the record, so a
runaway can be seen again with its whole thinking kept:

    python -m eval_harness.runaway repro <record> --attempt 1 --runs 2

It writes coach_artifacts/measurement_runaway_<id>.json per run."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import debate
from agent_client import JSON_CORRECTION, SCHEMA_PREFIX, schema_correction, send_once
from config import MODELS
from eval_harness.common import load_records, read_input

REPO_ROOT = Path(__file__).resolve().parent.parent
BRIDGE_DIFF = REPO_ROOT / "docs/fixtures/qttune_bridge_refactor.diff"
REPRO_MODE = "runaway_repro"

SHINGLE_WORDS = 12
# phrases that open another pass over the same material
RECHECK = re.compile(r"\b(?:let me (?:re-?read|re-?check|check|look|reconsider|verify|double-check)"
                     r"|actually|wait|looking at)\b", re.IGNORECASE)


def split_fences(text: str) -> Tuple[str, str]:
    """(prose, code): text outside ``` fences and text inside them."""
    parts = text.split("```")
    return " ".join(parts[0::2]), " ".join(parts[1::2])


def repeat_profile(text: str, k: int = SHINGLE_WORDS) -> Dict[str, float]:
    """Repetition of one text: the share of k-word shingles seen earlier
    (overall and per third), the longest run of repeated words, and where
    the first repeat starts (as a share of the text; 1.0 when none)."""
    words = text.split()
    n = len(words) - k + 1
    if n <= 0:
        return {"words": len(words), "repeat": 0.0, "thirds": [0.0, 0.0, 0.0],
                "longest": 0, "first": 1.0}
    seen, marks = set(), []
    for i in range(n):
        shingle = tuple(words[i:i + k])
        marks.append(shingle in seen)
        seen.add(shingle)
    longest = run = 0
    for m in marks:
        run = run + 1 if m else 0
        longest = max(longest, run)
    thirds = []
    for t in range(3):
        part = marks[t * n // 3:(t + 1) * n // 3]
        thirds.append(sum(part) / len(part) if part else 0.0)
    first = next((i for i, m in enumerate(marks) if m), None)
    return {"words": len(words), "repeat": sum(marks) / n, "thirds": thirds,
            "longest": longest + k - 1 if longest else 0,
            "first": 1.0 if first is None else first / n}


def profile(thinking: str) -> Dict[str, object]:
    """The prose and code profiles of one thinking, and its re-check rate
    (phrases that start another pass, per 1,000 prose words)."""
    prose, code = split_fences(thinking)
    p = repeat_profile(prose)
    return {"prose": p, "code": repeat_profile(code),
            "rechecks_per_k": 1000 * len(RECHECK.findall(prose)) / max(p["words"], 1)}


def attempts(records: List[tuple]) -> Tuple[List[dict], int]:
    """Every telemetry entry with whole thinking, labeled by record, round,
    role and attempt; and how many runaways carry only a tail."""
    out, tail_only = [], 0

    def walk(node, where):
        nonlocal tail_only
        if isinstance(node, dict):
            if "thinking" in node and "eval_count" in node:
                out.append({**where, "attempt": node.get("attempt"),
                            "eval_count": node.get("eval_count"),
                            "done_reason": node.get("done_reason"),
                            "outcome": node.get("outcome"),
                            "thinking": node["thinking"]})
            elif node.get("done_reason") == "length" and "eval_count" in node:
                tail_only += 1
            for key, value in node.items():
                walk(value, {**where, "role": key} if isinstance(value, list) else where)
        elif isinstance(node, list):
            for value in node:
                walk(value, where)

    for path, rec in records:
        walk(rec.get("outputs") or {}, {"record": rec.get("metadata", {}).get("debate_id", path)})
    return out, tail_only


def corrections(calls: List[dict], attempt: int) -> List[str]:
    """The user messages call_agent appended before the given attempt, from
    the recorded outcomes: none after a transport failure."""
    out = []
    for call in calls[:attempt]:
        outcome = call.get("outcome", "")
        if outcome.startswith("reply was not valid JSON"):
            out.append(JSON_CORRECTION)
        elif outcome.startswith(SCHEMA_PREFIX):
            out.append(schema_correction(outcome[len(SCHEMA_PREFIX):]))
    return out


def fixture_for(record: dict) -> Tuple[str, Optional[str]]:
    """(diff, index path) of a round-1 record's input: the bridge fixture
    with the committed index, or the corpus fixture whose diff it hashed."""
    from eval_harness import corpus
    want = record["inputs"].get("diff_sha256")
    bridge = read_input(str(BRIDGE_DIFF))
    if debate.text_sha256(bridge) == want:
        return bridge, None
    for fixture in corpus.load_manifest()["fixtures"]:
        diff = read_input(str(fixture["diff_path"]))
        if debate.text_sha256(diff) == want:
            return diff, str(fixture["index_path"])
    raise SystemExit("ERROR: the record's diff is no committed fixture")


def rebuild(record: dict, attempt: int) -> Tuple[List[dict], float, str]:
    """(messages, temperature, fingerprint) of a recorded round-1 attempt,
    refused unless today's prompt matches the record's and the rebuilt
    request has the recorded size."""
    meta = record.get("metadata", {})
    if meta.get("mode") != debate.MEASUREMENT_MODE:
        raise SystemExit(f"ERROR: repro reads round-1 records, not {meta.get('mode')}")
    calls = record["outputs"]["round_history"][0]["telemetry"]["reviewer"]
    if not 0 <= attempt < len(calls):
        raise SystemExit(f"ERROR: the record has {len(calls)} attempt(s)")
    diff, index_path = fixture_for(record)
    setup = debate._prepare(diff, "", record["inputs"].get("header_artifact", False),
                            index_path)
    fingerprint = debate._run_settings(setup, debate.MEASUREMENT_MODE, 1, {})["prompt_fingerprint"]
    if (debate.PROMPT_VERSION, fingerprint) != (meta.get("prompt_version"),
                                                meta.get("prompt_fingerprint")):
        raise SystemExit(f"ERROR: the record was sent at {meta.get('prompt_version')} "
                         f"({meta.get('prompt_fingerprint')}); today's prompt is "
                         f"{debate.PROMPT_VERSION} ({fingerprint})")
    transcript = debate._render_transcript(record["inputs"]["proposal"],
                                           setup.static_section, 1)
    messages = [{"role": "system", "content": setup.reviewer_prompt},
                {"role": "user", "content": transcript}]
    messages += [{"role": "user", "content": c} for c in corrections(calls, attempt)]
    size = sum(len(m["content"]) for m in messages)
    if size != calls[attempt]["prompt_chars"]:
        raise SystemExit(f"ERROR: rebuilt request is {size} chars, the record's "
                         f"{calls[attempt]['prompt_chars']}")
    return messages, calls[attempt]["temperature"], fingerprint


def repro(path: str, attempt: int, runs: int) -> List[Path]:
    """Re-send a recorded attempt runs times, one record per run."""
    [(_, record)] = load_records([path])
    messages, temperature, fingerprint = rebuild(record, attempt)
    source = record["metadata"].get("debate_id")
    out = []
    for run in range(runs):
        _, _, reason, _, stats = send_once(MODELS["code_reviewer"], messages, temperature,
                                           debate._validate_reviewer, attempt)
        rid = debate._new_id("runaway")
        rec = {"metadata": {"debate_id": rid, "mode": REPRO_MODE,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "source_record": source, "source_attempt": attempt,
                            "prompt_version": debate.PROMPT_VERSION,
                            "prompt_fingerprint": fingerprint,
                            "judge_version": debate.JUDGE_VERSION,
                            "model": MODELS["code_reviewer"]},
               "inputs": {k: record["inputs"].get(k) for k in
                          ("proposal", "diff_sha256", "header_artifact")},
               "outputs": {"outcome": reason or "ok",
                           "telemetry": {"reviewer": [stats]}}}
        target = Path("coach_artifacts") / f"measurement_{rid}.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[{run + 1}/{runs}] {target}: {stats['eval_count']} tokens, "
              f"{stats['done_reason']}, {stats['wall_s']:.0f} s, {stats['outcome'][:50]}")
        out.append(target)
    return out


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["repro"]:
        ap = argparse.ArgumentParser(prog="runaway repro")
        ap.add_argument("record")
        ap.add_argument("--attempt", type=int, default=0)
        ap.add_argument("--runs", type=int, default=1)
        ap.add_argument("--dry", action="store_true", help="rebuild and check only")
        args = ap.parse_args(argv[1:])
        if args.dry:
            [(_, record)] = load_records([args.record])
            messages, temperature, fingerprint = rebuild(record, args.attempt)
            print(f"rebuilt: {len(messages)} message(s), "
                  f"{sum(len(m['content']) for m in messages)} chars, "
                  f"temperature {temperature}, fingerprint {fingerprint}")
        else:
            repro(args.record, args.attempt, args.runs)
        return
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("records", nargs="+", help="record files or globs")
    args = ap.parse_args(argv)
    rows, tail_only = attempts(load_records(args.records))
    print(f"{len(rows)} attempt(s) with whole thinking; {tail_only} runaway(s) "
          "with only a tail (recorded before it was kept)")
    print(f"{'record':<34} {'role':<14} att {'tokens':>6} {'end':<6} "
          f"{'prose rep':>9} {'by third':<16} {'longest':>7} {'code rep':>8} {'rechk/k':>7}")
    for r in rows:
        pr = profile(r["thinking"])
        p, c = pr["prose"], pr["code"]
        end = "cap" if r["done_reason"] == "length" else "ok"
        print(f"{str(r['record'])[-34:]:<34} {str(r.get('role'))[:14]:<14} {r['attempt']:>3} "
              f"{r['eval_count']:>6} {end:<6} {p['repeat']:>9.3f} "
              f"{' '.join(f'{x:.2f}' for x in p['thirds']):<16} {p['longest']:>7} "
              f"{c['repeat']:>8.3f} {pr['rechecks_per_k']:>7.1f}")


if __name__ == "__main__":
    main()
