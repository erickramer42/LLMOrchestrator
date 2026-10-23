#!/usr/bin/env python3
"""round2.py — the round-2 pair measurement (ADR-0002, eleventh
measurement): collect samples, list them for scoring.

    python -m eval_harness.round2 run --proposal "..." --diff FILE [--runs N]
    python -m eval_harness.round2 score --diff FILE RECORD_OR_GLOB...
        [--symbols A,B,C] [--repo PATH --rev REV]

`run` calls debate.run_round2_pair: a debate's round 1, both agents, then
the round-2 reviewer twice on the same round-1 replies, once in each
feedback format (debate.CRITIQUES_ARM, debate.V9_ARM).

`score` lists each sample's round-1 replies and each arm's round-2
reviewer blockers as stored. A sample is compared only when both arms
answered on the first attempt. Each round-2 blocker is tagged by where
its subject first appeared, judged by the code-like identifiers in its
claim (never its quote):
- carried: a round-1 reviewer blocker names one of them;
- from-question: else a round-1 reviewer question does, including
  blockers demoted to questions;
- echo?: else a round-1 engineer item does;
- new: none does.
The tags are candidates for hand labelling, like round1's M2 candidates.
M1 (--symbols) and M2 work as in round1. Score round 1 itself with
eval_harness.round1, which reads these records too.
"""

import argparse
import re
import sys
import textwrap
import time
from typing import Callable, List, Optional

from debate import CRITIQUES_ARM, V9_ARM, _sha256, run_round2_pair
from eval_harness.round1 import (demoted_tail, load_records, m1_hits,
                                 m2_candidates, post_state_lacks, read_input)
from repo_context import _IDENT, _code_like, _removed_identifiers

ARMS = (CRITIQUES_ARM, V9_ARM)
ORIGINS = ("carried", "from-question", "echo?", "new")

_CLAIM = re.compile(r"claim: (.*?)(?=; file: |; quote: |$)", re.S)


# ============ run ============

def run(proposal: str, code_diff: str, code_context: str, header: bool,
        runs: int) -> None:
    for i in range(1, runs + 1):
        started = time.monotonic()
        res = run_round2_pair(proposal, code_diff, code_context,
                              header_artifact=header)
        arms = ", ".join(f"{name} {n}" for name, n in res["round2_blockers"].items())
        print(f"[{i}/{runs}] {res['record_path']}: round 1 {res['round1_blockers']} "
              f"blockers; round 2 {arms or 'not reached'}; "
              f"{res['attempts']} call(s), "
              f"{(time.monotonic() - started) / 60:.1f} min")
        failures = res.get("agent_failures", [])
        for failure in failures:
            print(f"    {failure}")
        if any("request failed" in f for f in failures):
            raise SystemExit("Stopping: the Ollama request failed. Is the "
                             "server up and both models pulled?")


# ============ score ============

def claim_text(item: str) -> str:
    """The claim of a flattened {claim, file, quote} blocker; a plain
    string is all claim."""
    m = _CLAIM.search(item)
    return m.group(1) if m else item


def names(item: str) -> set:
    return {n for n in _IDENT.findall(claim_text(item)) if _code_like(n)}


def origin(blocker: str, first: dict) -> str:
    """Where a round-2 blocker's subject first appeared in round 1."""
    ids = names(blocker)

    def named_by(out: dict, keys) -> bool:
        return any(ids & names(str(v)) for k in keys for v in out.get(k, []) or [])
    if named_by(first["reviewer"], ("blockers",)):
        return "carried"
    if named_by(first["reviewer"], ("questions", "nits")):
        return "from-question"
    if named_by(first.get("auto_engineer") or {}, ("blockers", "concerns", "questions")):
        return "echo?"
    return "new"


def reviewer_status(entry: dict) -> str:
    """'first', 'retry' or 'failed' for an entry's reviewer reply."""
    if entry["reviewer"].get("verdict") == "PARSE_FAILURE":
        return "failed"
    calls = entry["telemetry"]["reviewer"]
    return "first" if calls and calls[-1]["attempt"] == 0 else "retry"


def score_pairs(records: List[tuple], code_diff: str, symbols: List[str],
                lacks: Optional[Callable[[str], bool]]) -> dict:
    """records: (path, record) pairs. Returns the compared pairs, the
    samples whose round 1 converged, and the excluded records with the
    reason."""
    diff_hash = _sha256(code_diff)
    removed = _removed_identifiers(code_diff)
    rows, converged, excluded = [], [], []
    for path, rec in records:
        record_id = rec["metadata"]["debate_id"]
        outputs = rec["outputs"]
        if "round2_arms" not in outputs:
            excluded.append((record_id, "not a round-2 pair record"))
            continue
        if rec.get("inputs", {}).get("diff_sha256") != diff_hash:
            excluded.append((record_id, "another diff"))
            continue
        if outputs.get("agent_failures"):
            excluded.append((record_id, "agent failure"))
            continue
        first, arms = outputs["round_history"][0], outputs["round2_arms"]
        if not arms:
            converged.append(record_id)
            continue
        retried = [name for name in ARMS if reviewer_status(arms[name]) != "first"]
        if retried:
            excluded.append((record_id, "round-2 reply came from a retry ("
                             + ", ".join(retried) + ")"))
            continue

        def tag(text: str) -> dict:
            return {"text": text, "origin": origin(text, first),
                    "m1": m1_hits(text, symbols),
                    "m2": m2_candidates(text, removed, lacks) if lacks else []}
        scored = {}
        for name in ARMS:
            unquoted, hedged = demoted_tail(arms[name])
            scored[name] = {
                "blockers": [tag(str(b)) for b in
                             arms[name]["reviewer"].get("blockers", []) or []],
                "unquoted": [tag(q) for q in unquoted],
                "demoted": [tag(q) for q in hedged]}
        rows.append({"id": record_id, "path": str(path),
                     "round1_status": reviewer_status(first),
                     "round1": first, "arms": scored})
    return {"rows": rows, "converged": converged, "excluded": excluded}


def print_report(scores: dict, symbols: List[str], m2_on: bool) -> None:
    rows = scores["rows"]
    print(f"{'sample':<31} {'arm':<21} {'blockers':>8} "
          + " ".join(f"{o:>13}" for o in ORIGINS)
          + f" {'M1':>4} {'M2?':>4} {'#e':>3} {'#h':>3}")
    totals = {name: dict.fromkeys(("blockers", *ORIGINS, "m1", "m2", "e", "h"), 0)
              for name in ARMS}
    for r in rows:
        for name in ARMS:
            arm, t = r["arms"][name], totals[name]
            b = arm["blockers"]
            counts = {o: sum(1 for x in b if x["origin"] == o) for o in ORIGINS}
            m1 = sum(1 for x in b if x["m1"])
            m2 = sum(1 for x in b if x["m2"])
            for key, n in (("blockers", len(b)), *counts.items(), ("m1", m1),
                           ("m2", m2), ("e", len(arm["unquoted"])),
                           ("h", len(arm["demoted"]))):
                t[key] += n
            print(f"{r['id']:<31} {name:<21} {len(b):>8} "
                  + " ".join(f"{counts[o]:>13}" for o in ORIGINS)
                  + f" {m1 if symbols else '-':>4} {m2 if m2_on else '-':>4}"
                  f" {len(arm['unquoted']):>3} {len(arm['demoted']):>3}")

    n = len(rows)
    print(f"\ncompared {n} pair(s); round 1 converged in "
          f"{len(scores['converged'])} sample(s)")
    for name in ARMS:
        t = totals[name]
        print(f"{name}: {t['blockers']} blockers ("
              + ", ".join(f"{o} {t[o]}" for o in ORIGINS) + ")"
              + (f", M1 {t['m1']}" if symbols else "")
              + (f", M2 candidates {t['m2']}" if m2_on else "")
              + f", evidence-demoted {t['e']}, hedge-demoted {t['h']}")
    retried = [r["id"] for r in rows if r["round1_status"] != "first"]
    if retried:
        print(f"note: round 1's reviewer reply came from a retry in "
              f"{', '.join(retried)}; round 2 still compares like with like")
    for record_id in scores["converged"]:
        print(f"converged in round 1: {record_id}")
    for record_id, reason in scores["excluded"]:
        print(f"excluded {record_id}: {reason}")

    print("\nPer sample: round 1's reviewer blockers (R#), engineer items "
          "(E-b/E-c/E-q), then each arm's round-2 blockers; demoted ones as "
          "#e and #h. Origin tags need confirming by hand.")
    for r in rows:
        first = r["round1"]
        print(f"\n===== {r['id']}")
        listing = [(f"R#{i}", str(b)) for i, b in
                   enumerate(first["reviewer"].get("blockers", []) or [], 1)]
        engineer = first.get("auto_engineer") or {}
        for key, label in (("blockers", "E-b"), ("concerns", "E-c"),
                           ("questions", "E-q")):
            listing += [(f"{label}{i}", str(v)) for i, v in
                        enumerate(engineer.get(key, []) or [], 1)]
        for label, text in listing:
            print(f"  {label}: " + textwrap.shorten(text, width=150))
        for name in ARMS:
            arm = r["arms"][name]
            items = ([(f"#{i}", b) for i, b in enumerate(arm["blockers"], 1)]
                     + [(f"#e{i}", b) for i, b in enumerate(arm["unquoted"], 1)]
                     + [(f"#h{i}", b) for i, b in enumerate(arm["demoted"], 1)])
            print(f"  --- {name}: {len(arm['blockers'])} blocker(s)")
            for label, b in items:
                tags = [b["origin"]] if label[1:2].isdigit() else []
                tags += [f"M1 {', '.join(b['m1'])}"] if b["m1"] else []
                tags += [f"M2? {', '.join(b['m2'])}"] if b["m2"] else []
                print(f"  {label}" + (f"  [{'; '.join(tags)}]" if tags else ""))
                print(textwrap.fill(b["text"], width=96, initial_indent="      ",
                                    subsequent_indent="      "))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Round-2 pair measurement: collect and score samples")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Collect round-2 pair samples")
    run_p.add_argument("--proposal", required=True)
    run_p.add_argument("--diff", help="Path to the code diff")
    run_p.add_argument("--context", help="Path to surrounding code context")
    run_p.add_argument("--header", action="store_true",
                       help="Review target is header-only (C ABI stub)")
    run_p.add_argument("--runs", type=int, default=1)

    score_p = sub.add_parser("score", help="List round-2 blockers per arm")
    score_p.add_argument("records", nargs="+", metavar="RECORD",
                         help="Pair measurement records (globs allowed)")
    score_p.add_argument("--diff", required=True,
                         help="The diff the records reviewed; others are excluded")
    score_p.add_argument("--symbols", default="",
                         help="Comma-separated symbols for M1")
    score_p.add_argument("--repo", help="Target repo checkout, for M2")
    score_p.add_argument("--rev", help="The diff's post-state commit, for M2")

    args = parser.parse_args()
    if args.command == "run":
        if args.runs < 1:
            parser.error("--runs must be at least 1")
        run(args.proposal, read_input(args.diff) if args.diff else "",
            read_input(args.context) if args.context else "",
            args.header, args.runs)
    else:
        if bool(args.repo) != bool(args.rev):
            parser.error("--repo and --rev go together")
        sys.stdout.reconfigure(encoding="utf-8")
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        lacks = post_state_lacks(args.repo, args.rev) if args.repo else None
        print_report(score_pairs(load_records(args.records),
                                 read_input(args.diff), symbols, lacks),
                     symbols, m2_on=lacks is not None)
