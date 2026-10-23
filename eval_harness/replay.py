#!/usr/bin/env python3
"""replay.py — archived round-1 reviewer replies, re-judged offline under
deterministic judge variants (ADR-0002, thirteenth measurement). No model.

    python -m eval_harness.replay --diff FILE [--labels FILE] [--n 3 --k 2]
        RECORD_OR_GLOB...

Each record's round 1 is rebuilt as the reviewer's raw blockers: the
stored ones (#n) and those the evidence check (#en) and the hedge check
(#hn) demoted, recovered from the end of its questions. Each variant
re-judges every blocker against the diff's post-change lines, and the
labels file (eval_harness/labels.json, hand labels from ADR-0002) says
which are valid, so precision and recall are counted without a model
call. First attempts only, as in the scorers.

Variants, on top of the current judge's evidence and hedge checks:
- j7: the current judge. It must reproduce each record's stored split.
- gapped: a quote's lines may skip post-change lines, in order, within
  one hunk.
- linked: a blocker whose claim names code identifiers, none of which
  occurs anywhere in the hunk its quote comes from (removed lines and
  the hunk header included), is demoted. A claim that names none passes.
- vote: n samples merged. Blockers are linked when their quotes matched
  a shared post-change line of 8 or more non-space characters, and a
  group of linked blockers is kept when it spans at least k samples.
"""

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from adjudication import (_ANY_FILE_SOURCES, _HUNK_BREAK, HEDGE_PATTERNS,
                          MIN_QUOTE_CHARS, _match_file, _quote_fragments,
                          evidence_sources)
from debate import text_sha256
from diff_reader import DEV_NULL, read_diff
from eval_harness.common import (demoted_tail, load_records, parse_blocker,
                                 read_input, reviewer_status)
from retrieval import IDENT, code_like

LABELS_PATH = Path(__file__).with_name("labels.json")
FP_CLASSES = ("deletion", "removal-objection", "other-fp")
BASE_VARIANTS = ("j7", "gapped", "linked", "gapped+linked")


class Item(NamedTuple):
    sample: str   # record id
    key: str      # '#1' stored, '#e1' evidence-demoted, '#h1' hedge-demoted
    text: str
    blocker: dict  # common.parse_blocker
    label: Optional[str]


# ============ the diff ============

class Diff(NamedTuple):
    sources: Dict[str, List[str]]   # adjudication.evidence_sources
    hunk_ids: Dict[str, List[Set[str]]]  # per path, identifiers of each hunk


def read_hunks(code_diff: str) -> Dict[str, List[Set[str]]]:
    """Each file's hunks as the identifiers on all their lines, removed
    lines and the header's context included. Hunk i holds the lines
    after the i-th hunk break in the file's evidence source, so it
    tracks paths exactly as adjudication.evidence_sources does."""
    hunks: Dict[str, List[Set[str]]] = {}
    paths: List[str] = []
    after_minus = False
    for tag, text in read_diff(code_diff):
        if tag in ("---", "+++"):
            if tag == "---" or not after_minus:
                paths = []
            after_minus = tag == "---"
            if text != DEV_NULL and text not in paths:
                paths.append(text)
                hunks.setdefault(text, [set()])
            continue
        after_minus = False
        for p in paths:
            if tag == "@@":
                hunks[p].append(set())
            hunks[p][-1] |= set(IDENT.findall(text))
    return hunks


def load_diff(code_diff: str) -> Diff:
    return Diff(evidence_sources(code_diff), read_hunks(code_diff))


# ============ quotes ============

def locate(fragment: List[str], source: List[str], gapped: bool = False
           ) -> Optional[List[int]]:
    """Positions in source of the lines a quote fragment matched, or None.
    As adjudication._fragment_found: each quote line in consecutive
    source lines, or the joined quote in the joined source. With gapped,
    also each quote line in a later source line of the same hunk."""
    k = len(fragment)
    for j in range(len(source) - k + 1):
        if all(q in source[j + i] for i, q in enumerate(fragment)):
            return list(range(j, j + k))
    joined, starts, pos = " ".join(fragment), [], 0
    for line in source:
        starts.append(pos)
        pos += len(line) + 1
    at = " ".join(source).find(joined)
    if at >= 0:
        return [i for i, s in enumerate(starts)
                if s < at + len(joined) and s + len(source[i]) > at]
    if not gapped:
        return None
    start = 0
    for end in [i for i, s in enumerate(source) if s == _HUNK_BREAK] + [len(source)]:
        hits, q = [], 0
        for i in range(start, end):
            if q < k and fragment[q] in source[i]:
                hits.append(i)
                q += 1
        if q == k:
            return hits
        start = end + 1
    return None


def verify(blocker: dict, diff: Diff, gapped: bool = False
           ) -> Optional[Tuple[str, List[int]]]:
    """(source path, matched positions) when the quote is found where the
    evidence check looks for it, else None."""
    fragments = _quote_fragments(blocker.get("quote", ""))
    if not fragments or max(len(line.replace(" ", "")) for f in fragments
                            for line in f) < MIN_QUOTE_CHARS:
        return None
    path = _match_file(blocker.get("file", ""), diff.sources)
    for p in ([path] if path else []) + [s for s in _ANY_FILE_SOURCES
                                         if s in diff.sources]:
        spots = [locate(f, diff.sources[p], gapped) for f in fragments]
        if all(s is not None for s in spots):
            return p, sorted(set().union(*spots))
    return None


def linked(blocker: dict, diff: Diff, where: Tuple[str, List[int]]) -> bool:
    """Whether the claim names an identifier of the hunk its quote came
    from. A claim naming no code identifier, or a quote from a source
    with no hunks, passes."""
    ids = {n for n in IDENT.findall(blocker.get("claim", "")) if code_like(n)}
    path, positions = where
    if not ids or path not in diff.hunk_ids:
        return True
    source = diff.sources[path]
    hunks = {source[:i].count(_HUNK_BREAK) for i in positions}
    return bool(ids & set().union(*(diff.hunk_ids[path][h] for h in hunks)))


# ============ judging ============

def judge(item: Item, diff: Diff, variant: str) -> Tuple[Optional[str], Optional[tuple]]:
    """(why the variant demotes the blocker or None, where its quote
    matched). Evidence first, then linkage, then hedging, as a debate
    would run them."""
    gapped = "gapped" in variant
    where = verify(item.blocker, diff, gapped)
    if where is None:
        return "evidence", None
    if "linked" in variant and not linked(item.blocker, diff, where):
        return "link", where
    if HEDGE_PATTERNS.search(item.blocker["hedge_text"]):
        return "hedge", where
    return None, where


def raw_items(record: dict, labels: Dict[str, str]) -> List[Item]:
    """Round 1's reviewer blockers as the reviewer wrote them: stored,
    then evidence-demoted, then hedge-demoted."""
    first = record["outputs"]["round_history"][0]
    unquoted, hedged = demoted_tail(first)
    sample = record["metadata"]["debate_id"]
    keyed = ([(f"#{i}", b) for i, b in enumerate(first["reviewer"].get("blockers", []) or [], 1)]
             + [(f"#e{i}", b) for i, b in enumerate(unquoted, 1)]
             + [(f"#h{i}", b) for i, b in enumerate(hedged, 1)])
    return [Item(sample, key, str(text), parse_blocker(str(text)), labels.get(key))
            for key, text in keyed]


def stored_reason(key: str) -> Optional[str]:
    return {"#e": "evidence", "#h": "hedge"}.get(key[:2])


# ============ voting ============

def vote(groups: List[List[Tuple[Item, tuple]]], diff: Diff, k: int) -> List[Item]:
    """The kept blockers of several samples (one list per sample), merged:
    a blocker is kept when its group of linked blockers spans at least k
    samples. Two blockers are linked when their quotes matched a shared
    line of MIN_QUOTE_CHARS or more non-space characters."""
    members = [(s, item, where) for s, group in enumerate(groups) for item, where in group]
    parent = list(range(len(members)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owners: Dict[tuple, int] = {}
    for i, (_, _, (path, positions)) in enumerate(members):
        for p in positions:
            if len(diff.sources[path][p].replace(" ", "")) < MIN_QUOTE_CHARS:
                continue
            if (path, p) in owners:
                parent[root(i)] = root(owners[(path, p)])
            else:
                owners[(path, p)] = i
    spans: Dict[int, Set[int]] = {}
    for i, (s, _, _) in enumerate(members):
        spans.setdefault(root(i), set()).add(s)
    return [item for i, (_, item, _) in enumerate(members) if len(spans[root(i)]) >= k]


# ============ scoring ============

def review_stats(kept: List[Item]) -> dict:
    labels = [i.label for i in kept]
    return {"blockers": len(kept),
            "valid": sum(1 for x in labels if x in ("race", "gate")),
            "fp": sum(1 for x in labels if x in FP_CLASSES),
            "race": int("race" in labels), "gate": int("gate" in labels)}


def summarize(reviews: List[dict]) -> dict:
    n = len(reviews) or 1
    total = {key: sum(r[key] for r in reviews) for key in
             ("blockers", "valid", "fp", "race", "gate")}
    return {"reviews": len(reviews),
            "blockers_per_review": total["blockers"] / n,
            "valid_share": total["valid"] / total["blockers"] if total["blockers"] else None,
            "fp_per_review": total["fp"] / n,
            "race_found": total["race"] / n, "gate_found": total["gate"] / n}


def replay(records: List[tuple], code_diff: str, label_doc: dict,
           n: int = 3, k: int = 2) -> dict:
    """Every variant's per-review numbers, by sample set and pooled, the
    j7 reproduction check, and the blockers each base variant judges
    differently from j7."""
    diff = load_diff(code_diff)
    diff_hash = text_sha256(code_diff)
    samples: Dict[str, List[List[Item]]] = {}
    excluded, mismatches, unlabelled = [], [], []
    for path, rec in records:
        sample = rec["metadata"]["debate_id"]
        entry = label_doc["records"].get(sample)
        if rec.get("inputs", {}).get("diff_sha256") != diff_hash:
            excluded.append((sample, "another diff"))
        elif not rec["outputs"].get("round_history"):
            excluded.append((sample, "no round"))
        elif reviewer_status(rec["outputs"]["round_history"][0]) != "first":
            excluded.append((sample, "round-1 reply came from a retry"))
        elif entry is None:
            excluded.append((sample, "no labels"))
        else:
            items = raw_items(rec, entry["labels"])
            unlabelled += [(sample, i.key) for i in items if i.label is None]
            for i in items:
                reason, _ = judge(i, diff, "j7")
                if reason != stored_reason(i.key):
                    mismatches.append((sample, i.key, stored_reason(i.key), reason))
            samples.setdefault(entry["set"], []).append(items)

    results: Dict[str, Dict[str, dict]] = {}
    changes: Dict[str, List[tuple]] = {}
    for variant in BASE_VARIANTS:
        per_set: Dict[str, List[List[Tuple[Item, tuple]]]] = {}
        for set_name, set_samples in samples.items():
            for items in set_samples:
                kept = []
                for i in items:
                    reason, where = judge(i, diff, variant)
                    if reason is None:
                        kept.append((i, where))
                    if variant != "j7" and reason != stored_reason(i.key):
                        changes.setdefault(variant, []).append(
                            (i.sample, i.key, i.label, stored_reason(i.key), reason))
                per_set.setdefault(set_name, []).append(kept)
        singles = {s: [review_stats([i for i, _ in kept]) for kept in groups]
                   for s, groups in per_set.items()}
        votes = {s: [review_stats(vote([groups[j] for j in combo], diff, k))
                     for combo in itertools.combinations(range(len(groups)), n)]
                 for s, groups in per_set.items()}
        for name, by_set in ((variant, singles), (f"vote {k}-of-{n} @{variant}", votes)):
            results[name] = {s: summarize(r) for s, r in by_set.items()}
            results[name]["pooled"] = summarize([x for r in by_set.values() for x in r])
    return {"results": results, "changes": changes, "excluded": excluded,
            "mismatches": mismatches, "unlabelled": unlabelled,
            "samples": {s: len(v) for s, v in samples.items()}}


def _fmt(x) -> str:
    return "-" if x is None else f"{x:.2f}"


def print_report(out: dict) -> None:
    print("samples (first attempts): " + ", ".join(f"{s} {n}" for s, n in out["samples"].items()))
    for sample, why in out["excluded"]:
        print(f"excluded {sample}: {why}")
    for sample, key in out["unlabelled"]:
        print(f"UNLABELLED {sample} {key}")
    print(f"\nj7 reproduces the stored split: "
          f"{'yes' if not out['mismatches'] else 'NO'}")
    for sample, key, stored, now in out["mismatches"]:
        print(f"  {sample} {key}: stored {stored or 'kept'}, j7 {now or 'kept'}")

    sets = list(out["samples"]) + ["pooled"]
    for s in sets:
        print(f"\n== {s}")
        print(f"{'variant':<28} {'reviews':>7} {'blk/rev':>7} {'valid%':>7} "
              f"{'FP/rev':>7} {'race':>6} {'gate':>6}")
        for name, by_set in out["results"].items():
            r = by_set[s]
            share = "-" if r["valid_share"] is None else f"{100 * r['valid_share']:.0f}%"
            print(f"{name:<28} {r['reviews']:>7} {_fmt(r['blockers_per_review']):>7} "
                  f"{share:>7} {_fmt(r['fp_per_review']):>7} "
                  f"{_fmt(r['race_found']):>6} {_fmt(r['gate_found']):>6}")

    for variant, rows in out["changes"].items():
        print(f"\n{variant}: judged differently from the stored split")
        for sample, key, label, stored, now in rows:
            print(f"  {sample} {key} [{label}]: {stored or 'kept'} -> {now or 'kept'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-judge archived round-1 reviewer replies offline")
    parser.add_argument("records", nargs="+", metavar="RECORD",
                        help="Measurement or pair records (globs allowed)")
    parser.add_argument("--diff", required=True, help="The diff the records reviewed")
    parser.add_argument("--labels", default=str(LABELS_PATH))
    parser.add_argument("--n", type=int, default=3, help="Samples per voted review")
    parser.add_argument("--k", type=int, default=2, help="Samples a kept group must span")
    args = parser.parse_args()
    if not 1 <= args.k <= args.n:
        parser.error("need 1 <= k <= n")
    sys.stdout.reconfigure(encoding="utf-8")
    label_doc = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    print_report(replay(load_records(args.records), read_input(args.diff), label_doc,
                        args.n, args.k))


if __name__ == "__main__":
    main()
