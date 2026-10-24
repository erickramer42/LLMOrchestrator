#!/usr/bin/env python3
"""replay.py — archived round-1 reviewer replies, re-judged offline under
deterministic judge variants (ADR-0002, thirteenth measurement). No model.

    python -m eval_harness.replay --diff FILE [--labels FILE] [--n 3 --k 2]
        RECORD_OR_GLOB...
    python -m eval_harness.replay --corpus [--labels FILE] [--n 3 --k 2]
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
- removed: a removed-line exception (ADR-0002, fifteenth measurement). A
  quote the evidence check rejects is accepted when it is found in the
  named file's code as it read BEFORE the change (context and removed
  lines). removed+linked also applies the linkage check, to post-change
  and pre-change quotes alike; removed+said accepts a pre-change quote
  only when the claim names a removal (REMOVAL_WORDS).
- flinked: linked, with acronyms filtered out of the claim's identifiers
  (ADR-0002, fifteenth measurement, amendment). An acronym is a token of
  capital letters only (no digit, underscore or lowercase letter), such
  as PID or UI, which code_like counts as code; it counts as an
  identifier only when the review's index defines it as a type or
  constant name (SCONFIG). removed+said+flinked composes it with the
  removal-word exception.

With --corpus, the records are grouped by corpus fixture (by diff hash,
docs/fixtures/corpus.json), each judged against its own diff and scored
with eval_harness/corpus_labels.json: an item is valid when a label is a
known bug of its fixture or a class the labels call valid. Votes combine
samples of one fixture only. Recall is reported per known bug and as
the mean over bugs.
"""

import argparse
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from adjudication import (_ANY_FILE_SOURCES, _HUNK_BREAK, HEDGE_PATTERNS,
                          MIN_QUOTE_CHARS, UNFILED_SOURCE, _match_file,
                          _quote_fragments, _squash, evidence_sources)
from debate import text_sha256
from diff_reader import DEV_NULL, read_diff
from eval_harness.common import (demoted_tail, load_records, parse_blocker,
                                 read_input, reviewer_status)
from retrieval import IDENT, code_like

LABELS_PATH = Path(__file__).with_name("labels.json")
CORPUS_LABELS_PATH = Path(__file__).with_name("corpus_labels.json")
FP_CLASSES = ("deletion", "removal-objection", "other-fp")
BASE_VARIANTS = ("j7", "gapped", "linked", "gapped+linked",
                 "removed", "removed+linked", "removed+said",
                 "flinked", "gapped+flinked", "removed+said+flinked")
# A bare all-caps word (flinked): an acronym unless the index defines it.
ACRONYM = re.compile(r"[A-Z]+")
# A match in a file's pre-change code is keyed by its path behind this
# prefix, so vote and linked can tell the two sides apart.
BEFORE = "before:"
# What a claim says when it names a removal as the defect (removed+said).
# Fixed when the fifteenth measurement was registered, before scoring.
REMOVAL_WORDS = re.compile(
    r"\b(?:remov\w*|delet\w*|no longer|dropp\w*|eliminat\w*)", re.IGNORECASE)


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
    before: Dict[str, List[str]]    # pre-change code, as before_sources
    symbols: frozenset = frozenset()  # type and constant names the index defines


def index_symbols(index: dict) -> frozenset:
    """The type and constant names an index defines: flinked's test for
    whether an all-caps word is code."""
    return frozenset([t["name"] for t in index.get("types", [])]
                     + [c["name"] for c in index.get("constants", [])])


def before_sources(code_diff: str) -> Dict[str, List[str]]:
    """Each file's code as it read BEFORE the change: context and removed
    lines in order, with the hunk breaks evidence_sources puts in, so
    hunk i is the same hunk on both sides. Mirrors evidence_sources line
    for line, with '+' skipped instead of '-'."""
    files: Dict[str, List[str]] = {}
    paths: List[str] = []
    after_minus = False
    for tag, text in read_diff(code_diff):
        if tag in ("---", "+++"):
            if tag == "---" or not after_minus:
                paths = []
            after_minus = tag == "---"
            if text != DEV_NULL and text not in paths:
                paths.append(text)
                files.setdefault(text, [])
            continue
        after_minus = False
        if tag == "+":
            continue
        line = _HUNK_BREAK if tag == "@@" else text
        for p in paths or [UNFILED_SOURCE]:
            files.setdefault(p, []).append(line)
    return {p: [s for s in map(_squash, lines) if s] for p, lines in files.items()}


def _source(diff: "Diff", key: str) -> List[str]:
    """The lines a match key points into: pre-change for BEFORE keys."""
    if key.startswith(BEFORE):
        return diff.before[key[len(BEFORE):]]
    return diff.sources[key]


def _path(key: str) -> str:
    return key[len(BEFORE):] if key.startswith(BEFORE) else key


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


def load_diff(code_diff: str, symbols: frozenset = frozenset()) -> Diff:
    return Diff(evidence_sources(code_diff), read_hunks(code_diff),
                before_sources(code_diff), symbols)


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


def verify(blocker: dict, diff: Diff, gapped: bool = False, before: bool = False
           ) -> Optional[Tuple[str, List[int]]]:
    """(source key, matched positions) when the quote is found where the
    evidence check looks for it, else None. With before, the quote is
    looked for in the pre-change code instead, and the key carries the
    BEFORE prefix."""
    fragments = _quote_fragments(blocker.get("quote", ""))
    if not fragments or max(len(line.replace(" ", "")) for f in fragments
                            for line in f) < MIN_QUOTE_CHARS:
        return None
    sources = diff.before if before else diff.sources
    path = _match_file(blocker.get("file", ""), sources)
    for p in ([path] if path else []) + [s for s in _ANY_FILE_SOURCES
                                         if s in sources]:
        spots = [locate(f, sources[p], gapped) for f in fragments]
        if all(s is not None for s in spots):
            return (BEFORE + p if before else p), sorted(set().union(*spots))
    return None


def claim_identifiers(claim: str, diff: Diff, filtered: bool = False) -> Set[str]:
    """The code identifiers a claim names. With filtered, acronyms are
    left out unless the index defines them."""
    ids = {n for n in IDENT.findall(claim) if code_like(n)}
    if filtered:
        ids = {n for n in ids if not ACRONYM.fullmatch(n) or n in diff.symbols}
    return ids


def linked(blocker: dict, diff: Diff, where: Tuple[str, List[int]],
           filtered: bool = False) -> bool:
    """Whether the claim names an identifier of the hunk its quote came
    from. A claim naming no code identifier, or a quote from a source
    with no hunks, passes."""
    ids = claim_identifiers(blocker.get("claim", ""), diff, filtered)
    key, positions = where
    path = _path(key)
    if not ids or path not in diff.hunk_ids:
        return True
    source = _source(diff, key)
    hunks = {source[:i].count(_HUNK_BREAK) for i in positions}
    return bool(ids & set().union(*(diff.hunk_ids[path][h] for h in hunks)))


# ============ judging ============

def judge(item: Item, diff: Diff, variant: str) -> Tuple[Optional[str], Optional[tuple]]:
    """(why the variant demotes the blocker or None, where its quote
    matched). Evidence first, then linkage, then hedging, as a debate
    would run them."""
    parts = set(variant.split("+"))
    gapped = "gapped" in parts
    where = verify(item.blocker, diff, gapped)
    if where is None and "removed" in parts:
        before = verify(item.blocker, diff, gapped, before=True)
        if before is not None and ("said" not in parts
                                   or REMOVAL_WORDS.search(item.blocker["claim"])):
            where = before
    if where is None:
        return "evidence", None
    if (parts & {"linked", "flinked"}
            and not linked(item.blocker, diff, where, filtered="flinked" in parts)):
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
            if len(_source(diff, path)[p].replace(" ", "")) < MIN_QUOTE_CHARS:
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
           n: int = 3, k: int = 2, symbols: frozenset = frozenset()) -> dict:
    """Every variant's per-review numbers, by sample set and pooled, the
    j7 reproduction check, and the blockers each base variant judges
    differently from j7."""
    diff = load_diff(code_diff, symbols)
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


# ============ the corpus ============

def corpus_stats(kept: List[Item], bug_ids: Set[str], valid_classes: Set[str]) -> dict:
    """One review's kept blockers, scored with corpus labels (lists)."""
    tags = [set(i.label or []) for i in kept]
    valid = sum(1 for t in tags if t & bug_ids or t & valid_classes)
    return {"blockers": len(kept), "valid": valid, "fp": len(kept) - valid,
            "found": set().union(*(t & bug_ids for t in tags)) if tags else set()}


def summarize_corpus(reviews: List[dict], bug_ids: List[str]) -> dict:
    n = len(reviews)
    blockers = sum(r["blockers"] for r in reviews)
    valid = sum(r["valid"] for r in reviews)
    return {"reviews": n, "blockers": blockers, "valid": valid,
            "fp": sum(r["fp"] for r in reviews),
            "recall": {b: (sum(1 for r in reviews if b in r["found"]) / n if n else None)
                       for b in bug_ids}}


def pool_corpus(per_fixture: Dict[str, dict], kinds: Dict[str, str]) -> dict:
    """Pooled numbers: valid share and FPs per review over every fixture,
    mean recall over every known bug, FPs per review on clean fixtures."""
    rows = list(per_fixture.values())
    reviews = sum(r["reviews"] for r in rows)
    blockers = sum(r["blockers"] for r in rows)
    recalls = [x for r in rows for x in r["recall"].values() if x is not None]
    clean = [r for f, r in per_fixture.items() if kinds[f] == "clean"]
    clean_reviews = sum(r["reviews"] for r in clean)
    return {"reviews": reviews, "blockers": blockers,
            "valid_share": sum(r["valid"] for r in rows) / blockers if blockers else None,
            "fp_per_review": sum(r["fp"] for r in rows) / reviews if reviews else None,
            "mean_recall": sum(recalls) / len(recalls) if recalls else None,
            "clean_fp_per_review": (sum(r["fp"] for r in clean) / clean_reviews
                                    if clean_reviews else None)}


def replay_corpus(records: List[tuple], manifest: dict, label_doc: dict,
                  n: int = 3, k: int = 2) -> dict:
    """replay, for the corpus: each record judged against its fixture's
    diff, scored with corpus labels, voted within its fixture."""
    by_hash = {text_sha256(read_input(str(f["diff_path"]))): f
               for f in manifest["fixtures"]}
    valid_classes = set(label_doc.get("valid", []))
    slots: Dict[str, dict] = {}
    excluded, mismatches, unlabelled = [], [], []
    for path, rec in records:
        sample = rec["metadata"]["debate_id"]
        entry = label_doc["records"].get(sample)
        fixture = by_hash.get(rec.get("inputs", {}).get("diff_sha256"))
        if fixture is None:
            excluded.append((sample, "not a corpus diff"))
        elif not rec["outputs"].get("round_history"):
            excluded.append((sample, "no round"))
        elif reviewer_status(rec["outputs"]["round_history"][0]) != "first":
            excluded.append((sample, "round-1 reply came from a retry"))
        elif entry is None:
            excluded.append((sample, "no labels"))
        else:
            slot = slots.setdefault(fixture["id"], {
                "fixture": fixture, "samples": [],
                "diff": load_diff(read_input(str(fixture["diff_path"])), index_symbols(
                    json.loads(Path(fixture["index_path"]).read_text(encoding="utf-8"))
                    if fixture.get("index_path") else {}))})
            items = raw_items(rec, entry["labels"])
            unlabelled += [(sample, i.key) for i in items if i.label is None]
            for i in items:
                reason, _ = judge(i, slot["diff"], "j7")
                if reason != stored_reason(i.key):
                    mismatches.append((sample, i.key, stored_reason(i.key), reason))
            slot["samples"].append(items)

    kinds = {f: s["fixture"]["kind"] for f, s in slots.items()}
    results: Dict[str, dict] = {}
    changes: Dict[str, List[tuple]] = {}
    for variant in BASE_VARIANTS:
        vote_name = f"vote {k}-of-{n} @{variant}"
        results[variant], results[vote_name] = {}, {}
        for fid, slot in slots.items():
            bug_list = [b["id"] for b in slot["fixture"].get("known_bugs", [])]
            bug_ids = set(bug_list)
            kept_per_sample = []
            for items in slot["samples"]:
                kept = []
                for i in items:
                    reason, where = judge(i, slot["diff"], variant)
                    if reason is None:
                        kept.append((i, where))
                    if variant != "j7" and reason != stored_reason(i.key):
                        changes.setdefault(variant, []).append(
                            (i.sample, i.key, i.label, stored_reason(i.key), reason))
                kept_per_sample.append(kept)
            singles = [corpus_stats([i for i, _ in kept], bug_ids, valid_classes)
                       for kept in kept_per_sample]
            votes = [corpus_stats(vote([kept_per_sample[j] for j in combo], slot["diff"], k),
                                  bug_ids, valid_classes)
                     for combo in itertools.combinations(range(len(kept_per_sample)), n)]
            results[variant][fid] = summarize_corpus(singles, bug_list)
            results[vote_name][fid] = summarize_corpus(votes, bug_list)
        for name in (variant, vote_name):
            results[name]["pooled"] = pool_corpus(
                {f: r for f, r in results[name].items() if f != "pooled"}, kinds)
    return {"results": results, "changes": changes, "excluded": excluded,
            "mismatches": mismatches, "unlabelled": unlabelled,
            "samples": {f: len(s["samples"]) for f, s in slots.items()}}


def print_corpus_report(out: dict) -> None:
    print("samples (first attempts): " + ", ".join(f"{s} {n}" for s, n in out["samples"].items()))
    for sample, why in out["excluded"]:
        print(f"excluded {sample}: {why}")
    for sample, key in out["unlabelled"]:
        print(f"UNLABELLED {sample} {key}")
    print(f"\nj7 reproduces the stored split: "
          f"{'yes' if not out['mismatches'] else 'NO'}")
    for sample, key, stored, now in out["mismatches"]:
        print(f"  {sample} {key}: stored {stored or 'kept'}, j7 {now or 'kept'}")

    print("\n== pooled")
    print(f"{'variant':<28} {'reviews':>7} {'valid%':>7} {'FP/rev':>7} "
          f"{'recall':>7} {'cleanFP':>7}")
    for name, by_fixture in out["results"].items():
        p = by_fixture["pooled"]
        share = "-" if p["valid_share"] is None else f"{100 * p['valid_share']:.0f}%"
        print(f"{name:<28} {p['reviews']:>7} {share:>7} {_fmt(p['fp_per_review']):>7} "
              f"{_fmt(p['mean_recall']):>7} {_fmt(p['clean_fp_per_review']):>7}")
    for fid in out["samples"]:
        print(f"\n== {fid}")
        bugs = list(next(iter(out["results"].values()))[fid]["recall"])
        print(f"{'variant':<28} {'reviews':>7} {'blk/rev':>7} {'valid':>5} {'FP/rev':>7}  "
              + " ".join(f"{b[:14]:>14}" for b in bugs))
        for name, by_fixture in out["results"].items():
            r = by_fixture[fid]
            per = r["blockers"] / r["reviews"] if r["reviews"] else None
            fpr = r["fp"] / r["reviews"] if r["reviews"] else None
            print(f"{name:<28} {r['reviews']:>7} {_fmt(per):>7} {r['valid']:>5} "
                  f"{_fmt(fpr):>7}  "
                  + " ".join(f"{_fmt(r['recall'][b]):>14}" for b in bugs))
    for variant, rows in out["changes"].items():
        print(f"\n{variant}: judged differently from the stored split")
        for sample, key, label, stored, now in rows:
            print(f"  {sample} {key} {label}: {stored or 'kept'} -> {now or 'kept'}")


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
    parser.add_argument("--diff", help="The diff the records reviewed")
    parser.add_argument("--corpus", action="store_true",
                        help="Group records by corpus fixture, each judged "
                             "against its own diff, scored with corpus labels")
    parser.add_argument("--labels", help="Labels file (default: labels.json, "
                                         "or corpus_labels.json with --corpus)")
    parser.add_argument("--index", help="With --diff: the index whose type and "
                                        "constant names flinked treats as code "
                                        "(default: repo_context.json)")
    parser.add_argument("--n", type=int, default=3, help="Samples per voted review")
    parser.add_argument("--k", type=int, default=2, help="Samples a kept group must span")
    args = parser.parse_args()
    if not 1 <= args.k <= args.n:
        parser.error("need 1 <= k <= n")
    if bool(args.corpus) == bool(args.diff):
        parser.error("give --diff or --corpus, not both")
    sys.stdout.reconfigure(encoding="utf-8")
    labels = args.labels or str(CORPUS_LABELS_PATH if args.corpus else LABELS_PATH)
    label_doc = json.loads(Path(labels).read_text(encoding="utf-8"))
    if args.corpus:
        from eval_harness.corpus import load_manifest
        print_corpus_report(replay_corpus(load_records(args.records), load_manifest(),
                                          label_doc, args.n, args.k))
        return
    from retrieval import CONTEXT_PATH
    index = json.loads(Path(args.index or CONTEXT_PATH).read_text(encoding="utf-8"))
    print_report(replay(load_records(args.records), read_input(args.diff), label_doc,
                        args.n, args.k, index_symbols(index)))


if __name__ == "__main__":
    main()
