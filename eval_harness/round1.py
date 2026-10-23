#!/usr/bin/env python3
"""round1.py — round-1 reviewer measurements: collect samples, score them.

    python -m eval_harness.round1 run --proposal "..." --diff FILE [--runs N]
    python -m eval_harness.round1 score --diff FILE RECORD_OR_GLOB...
        [--symbols A,B,C] [--repo PATH --rev REV]

`run` calls debate.run_round1_review, so unlike probe.py and bakeoff.py
it uses agent_client, config and the debate's own transcript: each
sample is a debate's first reviewer call, saved as
coach_artifacts/measurement_*.json.

`score` reads measurement and debate records alike, since round 1 of a
debate is the same sample. It scores the reviewer's round-1 blockers as
stored (after hedge demotion), first attempts only (ADR-0002, fifth
measurement):

- M1: blockers naming a --symbols identifier (whole word, case-sensitive).
- M2 candidates: blockers naming a code-like identifier that only the
  diff's removed lines contain and that the post-state tree (--repo at
  --rev) lacks. M2 itself is adjudicated: a blocker that objects to a
  removal, without claiming the removed code survives, is not a
  deletion-consistency FP. Confirm each candidate by hand.

Demoted blockers are listed separately and are not counted as blockers.
They are recovered from the tail of round 1's questions using the
evidence_demotions (judge j3) and hedge_demotions counts, in that order.
"""

import textwrap
from typing import Callable, List, Optional

from debate import run_round1_review, text_sha256
from eval_harness.common import (demoted_tail, m1_hits, m2_candidates, main,
                                 reviewer_status)
from retrieval import removed_identifiers


# ============ score ============

def score_records(records: List[tuple], code_diff: str, symbols: List[str],
                  lacks: Optional[Callable[[str], bool]]) -> dict:
    """records: (path, record) pairs. Returns scored rows and the
    excluded records with the reason. A record is scored only if it
    reviewed this exact diff and its round-1 reviewer answered on the
    first attempt (or predates telemetry, which is flagged)."""
    diff_hash = text_sha256(code_diff)
    removed = removed_identifiers(code_diff)
    rows, excluded = [], []
    for path, rec in records:
        meta = rec["metadata"]
        record_id = meta["debate_id"]
        recorded_hash = rec.get("inputs", {}).get("diff_sha256")
        if recorded_hash != diff_hash:
            excluded.append((record_id, "no diff hash" if recorded_hash is None
                             else "another diff"))
            continue
        if not rec["outputs"]["round_history"]:
            excluded.append((record_id, "input refused, no round"))
            continue
        first_round = rec["outputs"]["round_history"][0]
        status = reviewer_status(first_round)
        if status in ("retry", "failed"):
            excluded.append((record_id, "reviewer failed" if status == "failed"
                             else "round-1 reviewer reply came from a retry"))
            continue
        reviewer = first_round["reviewer"]
        unquoted, demoted = demoted_tail(first_round)

        def tag(text: str) -> dict:
            return {"text": text, "m1": m1_hits(text, symbols),
                    "m2": m2_candidates(text, removed, lacks) if lacks else []}
        rows.append({"id": record_id, "path": str(path), "status": status,
                     "prompt_version": meta.get("prompt_version"),
                     "fingerprint": meta.get("prompt_fingerprint"),
                     "blockers": [tag(str(b)) for b in
                                  reviewer.get("blockers", []) or []],
                     "unquoted": [tag(q) for q in unquoted],
                     "demoted": [tag(q) for q in demoted]})
    return {"rows": rows, "excluded": excluded}


def print_report(scores: dict, symbols: List[str], m2_on: bool) -> None:
    rows = scores["rows"]
    print(f"{'record':<31} {'prompt':<22} {'attempt':<8} "
          f"{'blockers':>8} {'M1':>4} {'M2?':>4} {'unquoted':>8} {'hedged':>6}")
    totals = {"blockers": 0, "m1": 0, "m2": 0, "unquoted": 0, "demoted": 0}
    for r in rows:
        b = r["blockers"]
        m1 = sum(1 for x in b if x["m1"])
        m2 = sum(1 for x in b if x["m2"])
        totals["blockers"] += len(b)
        totals["m1"] += m1
        totals["m2"] += m2
        totals["unquoted"] += len(r["unquoted"])
        totals["demoted"] += len(r["demoted"])
        print(f"{r['id']:<31} {str(r['prompt_version']):<22} {r['status']:<8} "
              f"{len(b):>8} {m1 if symbols else '-':>4} {m2 if m2_on else '-':>4} "
              f"{len(r['unquoted']):>8} {len(r['demoted']):>6}")

    n = len(rows)
    print(f"\nscored {n} record(s): {totals['blockers']} blockers"
          + (f", M1 {totals['m1']}" if symbols else "")
          + (f", M2 candidates {totals['m2']}" if m2_on else "")
          + f", evidence-demoted {totals['unquoted']}"
          + f", hedge-demoted {totals['demoted']}")
    if n:
        print(f"per run: blockers {totals['blockers'] / n:.2f}"
              + (f", M1 {totals['m1'] / n:.2f}" if symbols else "")
              + (f", M2 candidates {totals['m2'] / n:.2f}" if m2_on else ""))
    unknown = sum(1 for r in rows if r["status"] == "unknown")
    if unknown:
        print(f"note: {unknown} record(s) predate telemetry; whether their "
              "round-1 reply was a first attempt is unknown")
    fingerprints = sorted({str(r["fingerprint"]) for r in rows})
    if len(fingerprints) > 1:
        print(f"WARNING: the scored records span {len(fingerprints)} prompt "
              f"fingerprints ({', '.join(fingerprints)}); score each arm "
              "separately")
    for record_id, reason in scores["excluded"]:
        print(f"excluded {record_id}: {reason}")

    print("\nRound-1 blockers (M2 candidates need confirming: an objection to "
          "a removal is not M2). Demoted blockers follow each record's "
          "blockers: evidence-demoted as #e1, #e2, ..., hedge-demoted as #h1, ...")
    for r in rows:
        items = ([(f"#{i}", b) for i, b in enumerate(r["blockers"], 1)]
                 + [(f"#e{i}", b) for i, b in enumerate(r["unquoted"], 1)]
                 + [(f"#h{i}", b) for i, b in enumerate(r["demoted"], 1)])
        for label, b in items:
            tags = [f"M1 {', '.join(b['m1'])}"] if b["m1"] else []
            tags += [f"M2? {', '.join(b['m2'])}"] if b["m2"] else []
            print(f"\n{r['id']} {label}" + (f"  [{'; '.join(tags)}]" if tags else ""))
            print(textwrap.fill(b["text"], width=96, initial_indent="    ",
                                subsequent_indent="    "))


def _summary(res: dict) -> str:
    return f"{res['blockers']} blockers, {res['attempts']} attempt(s)"


if __name__ == "__main__":
    main("round-1 reviewer", run_round1_review, _summary,
         "the reviewer model", score_records, print_report,
         score_help="Score round-1 reviewer blockers",
         records_help="Decision or measurement records (globs allowed)")
