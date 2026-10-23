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

import re
import textwrap
from typing import Callable, List, Optional

from debate import CRITIQUES_ARM, V9_ARM, run_round2_pair, text_sha256
from eval_harness.common import (demoted_tail, m1_hits, m2_candidates, main,
                                 reviewer_status)
from retrieval import IDENT, code_like, removed_identifiers

ARMS = (CRITIQUES_ARM, V9_ARM)
ORIGINS = ("carried", "from-question", "echo?", "new")

_CLAIM = re.compile(r"claim: (.*?)(?=; file: |; quote: |$)", re.S)


# ============ score ============

def claim_text(item: str) -> str:
    """The claim of a flattened {claim, file, quote} blocker; a plain
    string is all claim."""
    m = _CLAIM.search(item)
    return m.group(1) if m else item


def names(item: str) -> set:
    return {n for n in IDENT.findall(claim_text(item)) if code_like(n)}


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


def score_pairs(records: List[tuple], code_diff: str, symbols: List[str],
                lacks: Optional[Callable[[str], bool]]) -> dict:
    """records: (path, record) pairs. Returns the compared pairs, the
    samples whose round 1 converged, and the excluded records with the
    reason."""
    diff_hash = text_sha256(code_diff)
    removed = removed_identifiers(code_diff)
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
        if not outputs["round_history"]:
            excluded.append((record_id, "input refused, no round"))
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


def _summary(res: dict) -> str:
    arms = ", ".join(f"{name} {n}" for name, n in res["round2_blockers"].items())
    return (f"round 1 {res['round1_blockers']} blockers; round 2 "
            f"{arms or 'not reached'}; {res['attempts']} call(s)")


if __name__ == "__main__":
    main("round-2 pair", run_round2_pair, _summary, "both models",
         score_pairs, print_report,
         score_help="List round-2 blockers per arm",
         records_help="Pair measurement records (globs allowed)")
