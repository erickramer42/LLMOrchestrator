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

import argparse
import functools
import glob
import json
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from debate import _sha256, run_round1_review
from repo_context import _IDENT, _code_like, _removed_identifiers


def read_input(path: str) -> str:
    """Read as orchestrator.py does, so the diff hashes match the records."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SystemExit(f"ERROR: cannot read {path}: {exc}")


# ============ run ============

def run(proposal: str, code_diff: str, code_context: str, header: bool,
        runs: int) -> None:
    for i in range(1, runs + 1):
        started = time.monotonic()
        res = run_round1_review(proposal, code_diff, code_context,
                                header_artifact=header)
        print(f"[{i}/{runs}] {res['record_path']}: {res['blockers']} blockers, "
              f"{res['attempts']} attempt(s), "
              f"{(time.monotonic() - started) / 60:.1f} min")
        failures = res.get("agent_failures", [])
        for failure in failures:
            print(f"    {failure}")
        # A runaway that exhausts its retries is a result worth keeping;
        # an unreachable server would only fill coach_artifacts/ with
        # failure records.
        if any("request failed" in f for f in failures):
            raise SystemExit("Stopping: the Ollama request failed. Is the "
                             "server up and the reviewer model pulled?")


# ============ score ============

def attempt_status(record: dict) -> str:
    """How round 1's reviewer reply was obtained: 'first', 'retry' or
    'failed'. 'unknown' for records without telemetry (before v5.2)."""
    first_round = record["outputs"]["round_history"][0]
    if first_round["reviewer"].get("verdict") == "PARSE_FAILURE":
        return "failed"
    calls = (first_round.get("telemetry") or {}).get("reviewer")
    if not calls:
        return "unknown"
    return "first" if calls[-1]["attempt"] == 0 else "retry"


def demoted_tail(entry: dict) -> Tuple[List[str], List[str]]:
    """(evidence-demoted, hedge-demoted) reviewer blockers of one round
    entry. Demoted blockers end the reviewer's questions: evidence
    demotions (judge j3 on), then hedge demotions, each as many as
    recorded."""
    n_hedged = (entry.get("hedge_demotions") or {}).get("reviewer_demoted", 0)
    n_unquoted = (entry.get("evidence_demotions") or {}).get("reviewer_demoted", 0)
    questions = [str(q) for q in entry["reviewer"].get("questions", []) or []]
    tail = (questions[len(questions) - n_unquoted - n_hedged:]
            if n_unquoted + n_hedged else [])
    return tail[:n_unquoted], tail[n_unquoted:]


def m1_hits(blocker: str, symbols: List[str]) -> List[str]:
    return [s for s in symbols if re.search(rf"\b{re.escape(s)}\b", blocker)]


def m2_candidates(blocker: str, removed: set,
                  lacks: Callable[[str], bool]) -> List[str]:
    """Identifiers the blocker names that only the diff's removed lines
    contain and the post-state lacks. English words are skipped: the
    removed lines' comments contain plenty of them."""
    names = set(_IDENT.findall(blocker)) & removed
    return sorted(n for n in names if _code_like(n) and lacks(n))


def post_state_lacks(repo: str, rev: str) -> Callable[[str], bool]:
    """lacks(name): True when `git grep -w` finds name nowhere in repo at
    rev, the check ADR-0002 used by hand."""
    check = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q",
                            f"{rev}^{{commit}}"], capture_output=True, text=True)
    if check.returncode != 0:
        raise SystemExit(f"ERROR: {rev} is not a commit in {repo}")

    @functools.lru_cache(maxsize=None)
    def lacks(name: str) -> bool:
        r = subprocess.run(["git", "-C", repo, "grep", "-q", "-w", "-F",
                            "-e", name, rev], capture_output=True, text=True)
        if r.returncode not in (0, 1):
            raise SystemExit(f"ERROR: git grep at {rev} failed: {r.stderr.strip()}")
        return r.returncode == 1
    return lacks


def score_records(records: List[tuple], code_diff: str, symbols: List[str],
                  lacks: Optional[Callable[[str], bool]]) -> dict:
    """records: (path, record) pairs. Returns scored rows and the
    excluded records with the reason. A record is scored only if it
    reviewed this exact diff and its round-1 reviewer answered on the
    first attempt (or predates telemetry, which is flagged)."""
    diff_hash = _sha256(code_diff)
    removed = _removed_identifiers(code_diff)
    rows, excluded = [], []
    for path, rec in records:
        meta = rec["metadata"]
        record_id = meta["debate_id"]
        recorded_hash = rec.get("inputs", {}).get("diff_sha256")
        if recorded_hash != diff_hash:
            excluded.append((record_id, "no diff hash" if recorded_hash is None
                             else "another diff"))
            continue
        status = attempt_status(rec)
        if status in ("retry", "failed"):
            excluded.append((record_id, "reviewer failed" if status == "failed"
                             else "round-1 reviewer reply came from a retry"))
            continue
        first_round = rec["outputs"]["round_history"][0]
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


def load_records(patterns: List[str]) -> List[tuple]:
    """(path, record) pairs for every file the patterns match, in name
    order. Patterns are expanded here because PowerShell does not."""
    paths = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if not matches:
            raise SystemExit(f"ERROR: no records match {pattern}")
        paths += [p for p in matches if p not in paths]
    records = []
    for p in paths:
        try:
            records.append((p, json.loads(Path(p).read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"ERROR: cannot read record {p}: {exc}")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Round-1 reviewer measurements: collect and score samples")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Collect round-1 reviewer samples")
    run_p.add_argument("--proposal", required=True)
    run_p.add_argument("--diff", help="Path to the code diff")
    run_p.add_argument("--context", help="Path to surrounding code context")
    run_p.add_argument("--header", action="store_true",
                       help="Review target is header-only (C ABI stub)")
    run_p.add_argument("--runs", type=int, default=1)

    score_p = sub.add_parser("score", help="Score round-1 reviewer blockers")
    score_p.add_argument("records", nargs="+", metavar="RECORD",
                         help="Decision or measurement records (globs allowed)")
    score_p.add_argument("--diff", required=True,
                         help="The diff the records reviewed; others are excluded")
    score_p.add_argument("--symbols", default="",
                         help="Comma-separated frozen symbol set for M1")
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
        # Blocker text is model output; redirected to a file on Windows the
        # default cp1252 would crash on the first arrow or math sign.
        sys.stdout.reconfigure(encoding="utf-8")
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        lacks = post_state_lacks(args.repo, args.rev) if args.repo else None
        print_report(score_records(load_records(args.records),
                                   read_input(args.diff), symbols, lacks),
                     symbols, m2_on=lacks is not None)
