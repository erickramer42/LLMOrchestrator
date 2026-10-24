"""repair.py — the repair pass measured paired on archived round-1 replies
(ADR-0002, seventeenth measurement).

    python -m eval_harness.repair run --set corpus|bridge
    python -m eval_harness.repair score --set corpus|bridge
    python -m eval_harness.repair ceiling --set corpus|bridge

For each labelled first-attempt record, `run` rebuilds the round-1
request a debate sends today (debate._prepare and _render_transcript
from the committed fixture and the record's proposal), re-judges the
record's raw reviewer items with judge j8 (replay's flinked), offers the
quote failures exactly as a debate would (debate.repair_offer), and makes
the repair call (debate.repair_call), saving
coach_artifacts/measurement_repair_<source>.json. Records with nothing
to offer get no call and no file. A source with a file is skipped, so a
stopped batch resumes.

`score` compares arm A, the j8 split, with arm B, the split after
repair, on the same replies. A restored item keeps its claim, so its
label is the original item's. Reported: corpus valid share, FPs per
review, mean recall per known bug and FPs per clean review; bridge FPs
per review, race and gate found; and every offered item by its label
class, the quote group it came from ('before': found only in the code
before the change; 'nowhere') and its result.

`ceiling` (ADR-0002, eighteenth measurement, Step 0) calls no model: for
every item `run` offers, it tries each post-change line of the diff as a
one-line repair through debate.apply_repairs, and reports which items
some quote would restore (judge-quotable), which a quote naming one of
the claim's identifiers would (on-point), which the hedge check blocks
whatever the quote, and the arms with those items restored ('on-point'
counts claims naming no identifier, which pass linkage anywhere;
'named' leaves them out).
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import debate
from adjudication import _HUNK_BREAK, JUDGE_VERSION, claim_identifiers
from config import MODELS
from eval_harness import replay
from eval_harness.common import load_records, read_input, reviewer_status
from retrieval import IDENT

BRIDGE_DIFF = "docs/fixtures/qttune_bridge_refactor.diff"
SETS = {
    "corpus": ["coach_artifacts/measurement_round1_20261024_0[0-4]*.json"],
    "bridge": ["coach_artifacts/measurement_round1_20261023_01*.json",
               "coach_artifacts/measurement_round2_20261023_*.json"],
}
OUT_DIR = Path("coach_artifacts")


def repair_fingerprint() -> str:
    return debate.text_sha256(debate.REPAIR_TEMPLATE + debate.REPAIR_ITEM_TEMPLATE
                              + "".join(debate.REPAIR_REASONS.values()))[:16]


# ============ the samples ============

def samples(set_name: str) -> List[dict]:
    """Each labelled first-attempt record of the set, with what its repair
    call is built from: the record, its labels, the fixture (corpus) or
    None (bridge), the diff and the index path."""
    from eval_harness.corpus import load_manifest
    records = load_records(SETS[set_name])
    if set_name == "corpus":
        labels = json.loads(replay.CORPUS_LABELS_PATH.read_text(encoding="utf-8"))
        by_hash = {debate.text_sha256(read_input(str(f["diff_path"]))): f
                   for f in load_manifest()["fixtures"]}
    else:
        labels = json.loads(replay.LABELS_PATH.read_text(encoding="utf-8"))
        bridge_hash = debate.text_sha256(read_input(BRIDGE_DIFF))
    out = []
    for _, rec in records:
        rid = rec["metadata"]["debate_id"]
        entry = labels["records"].get(rid)
        rounds = rec["outputs"].get("round_history") or []
        if entry is None or not rounds or reviewer_status(rounds[0]) != "first":
            continue
        if set_name == "corpus":
            fixture = by_hash.get(rec["inputs"].get("diff_sha256"))
            if fixture is None:
                continue
            diff_path, index_path = str(fixture["diff_path"]), str(fixture["index_path"])
        else:
            if rec["inputs"].get("diff_sha256") != bridge_hash:
                continue
            fixture, diff_path, index_path = None, BRIDGE_DIFF, None
        out.append({"id": rid, "record": rec, "labels": entry["labels"],
                    "fixture": fixture, "diff_path": diff_path,
                    "index_path": index_path})
    return out


def judged_items(sample: dict, rdiff: replay.Diff) -> List[Tuple[replay.Item, Optional[str]]]:
    """The record's raw reviewer items, each with j8's reason (None: kept)."""
    return [(i, replay.judge(i, rdiff, "flinked")[0])
            for i in replay.raw_items(sample["record"], sample["labels"])]


def _evidence(item: replay.Item) -> Optional[dict]:
    b = item.blocker
    if not b["quote"] and not b["file"]:
        return None  # a plain string: no evidence, never offered (as in a debate)
    return {"file": b["file"], "quote": b["quote"], "claim": b["hedge_text"],
            "assertion": b["claim"]}


def _symbols(index_path: Optional[str]) -> frozenset:
    from retrieval import CONTEXT_PATH
    return replay.index_symbols(json.loads(
        Path(index_path or CONTEXT_PATH).read_text(encoding="utf-8")))


# ============ run ============

def _offer(sample: dict):
    """The review's setup, its j8-judged items, and what a debate offers
    the repair call: the quote failures with evidence, in order."""
    code_diff = read_input(sample["diff_path"])
    setup = debate._prepare(code_diff, "", False, sample["index_path"])
    rdiff = replay.load_diff(code_diff, _symbols(sample["index_path"]))
    items = judged_items(sample, rdiff)
    demoted = [{"blocker": i.text, "evidence": _evidence(i), "reason": "quote", "key": i.key}
               for i, reason in items if reason == "evidence" and _evidence(i)]
    return setup, items, demoted, debate.repair_offer(setup, demoted)


def run(set_name: str, dry: bool = False) -> None:
    """dry: list each record's offer and request size, call nothing."""
    for sample in samples(set_name):
        out_path = OUT_DIR / f"measurement_repair_{sample['id']}.json"
        if out_path.exists():
            print(f"{sample['id']}: done before, skipped")
            continue
        setup, items, demoted, offered = _offer(sample)
        if not offered:
            print(f"{sample['id']}: nothing to offer")
            continue
        assert len(offered) == len(demoted)
        proposal = sample["record"]["inputs"]["proposal"]
        transcript = debate._render_transcript(proposal, setup.static_section, 1)
        if dry:
            chars = len(setup.reviewer_prompt) + len(
                debate.repair_request(setup, transcript, offered))
            print(f"{sample['id']}: offer {len(offered)} "
                  f"({', '.join(o['why'] for o in offered)}), request {chars} chars")
            continue
        telemetry: List[dict] = []
        started = time.monotonic()
        repairs, skipped = debate.repair_call(setup, transcript, offered, telemetry)
        outcomes = debate.apply_repairs(setup, offered, repairs or [])
        record = {
            "metadata": {
                "mode": "repair_pair", "source_record": sample["id"], "set": set_name,
                "fixture": sample["fixture"]["id"] if sample["fixture"] else "bridge",
                "prompt_version": debate.REPAIR_VERSION, "judge_version": JUDGE_VERSION,
                "repair_fingerprint": repair_fingerprint(),
                "model": MODELS["code_reviewer"],
                "temperature": debate.TEMPERATURE_RETRY,
                "created": datetime.now(timezone.utc).isoformat()},
            # repair_offer keeps every demoted item here, in order
            "offered": [{"id": o["id"], "key": d["key"], "why": o["why"],
                         "blocker": o["blocker"]} for o, d in zip(offered, demoted)],
            "repairs": repairs, "skipped": skipped,
            "outcomes": [{k: v for k, v in x.items() if k != "blocker"}
                         if repairs is not None else dict(x, result="skipped")
                         for x in outcomes],
            "telemetry": telemetry,
        }
        for row, x in zip(record["outcomes"], outcomes):
            row["restored_blocker"] = x["blocker"]
        out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        restored = sum(1 for x in outcomes if x["blocker"])
        print(f"{sample['id']}: offered {len(offered)}, restored {restored}"
              + (f", skipped: {skipped}" if skipped else "")
              + f", {(time.monotonic() - started) / 60:.1f} min")
        if skipped and "request failed" in skipped:
            raise SystemExit("Stopping: the Ollama request failed. Is the server up?")


# ============ ceiling ============

def ceiling(set_name: str) -> dict:
    """Step 0 of the eighteenth measurement: what any repair could
    restore. Each offered item is tried with every post-change line of
    every file as a one-line repair, judged by debate.apply_repairs."""
    corpus_labels = json.loads(replay.CORPUS_LABELS_PATH.read_text(encoding="utf-8"))
    valid_classes = set(corpus_labels.get("valid", []))
    arms: Dict[str, Dict[str, list]] = {"A": {}, "judge": {}, "on-point": {}, "named": {}}
    rows = []
    for sample in samples(set_name):
        setup, items, demoted, offered = _offer(sample)
        candidates = [(path, line) for path, lines in setup.evidence.items()
                      for line in lines if line != _HUNK_BREAK]
        label_of = {i.key: i.label for i, _ in items}
        quotable, on_point, named = set(), set(), set()
        for o, d in zip(offered, demoted):
            ids = claim_identifiers(o["evidence"].get("assertion", ""), setup.symbols)
            results, passing = Counter(), []
            for path, line in candidates:
                out = debate.apply_repairs(setup, [o], [{"id": o["id"], "file": path,
                                                         "quote": line}])[0]
                results[out["result"]] += 1
                if out["blocker"]:
                    passing.append(line)
            pointed = [ln for ln in passing if ids & set(IDENT.findall(ln))]
            if passing:
                quotable.add(d["key"])
            if pointed or (passing and not ids):
                on_point.add(d["key"])
            if pointed:
                named.add(d["key"])
            rows.append({"source": sample["id"], "key": d["key"], "why": o["why"],
                         "class": _item_class(set_name, sample, label_of.get(d["key"]),
                                              valid_classes),
                         "label": label_of.get(d["key"]), "ids": sorted(ids),
                         "hedged": results["hedge"] > 0, "passing": len(passing),
                         "on_point": len(pointed), "results": dict(results),
                         "example": (pointed or passing or [None])[0]})
        kept = [i for i, reason in items if reason is None]
        group = sample["fixture"]["id"] if sample["fixture"] else "bridge"
        for arm, keys in (("A", set()), ("judge", quotable), ("on-point", on_point),
                          ("named", named)):
            arms[arm].setdefault(group, []).append(
                kept + [i for i, _ in items if i.key in keys])
    return {"set": set_name, "items": rows, "arms": _pool_arms(set_name, arms)}


def print_ceiling(res: dict) -> None:
    rows = res["items"]
    print(f"set: {res['set']}; offered items {len(rows)}")
    print("\nitems by class and quote group: offered, hedged, judge-quotable, "
          "on-point, naming no identifier")
    cells = sorted({(r["class"], r["why"]) for r in rows})
    for cls, why in cells + [("all", "")]:
        sel = [r for r in rows if cls == "all" or (r["class"], r["why"]) == (cls, why)]
        print(f"   {cls:<12} {why:<8} {len(sel):>3} {sum(r['hedged'] for r in sel):>3} "
              f"{sum(r['passing'] > 0 for r in sel):>3} "
              f"{sum(r['on_point'] > 0 or (r['passing'] > 0 and not r['ids']) for r in sel):>3} "
              f"{sum(not r['ids'] for r in sel):>3}")
    for arm, a in res["arms"].items():
        print(f"arm {arm}: " + ", ".join(
            f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}" for k, v in a.items()))
    base = res["arms"]["A"]
    for arm in ("judge", "on-point", "named"):
        b = res["arms"][arm]
        if res["set"] == "corpus":
            print(f"delta {arm}: recall {b['mean_recall'] - base['mean_recall']:+.3f}, "
                  f"FPs per review {b['fp_per_review'] - base['fp_per_review']:+.3f}")
        else:
            print(f"delta {arm}: FPs per review "
                  f"{b['fp_per_review'] - base['fp_per_review']:+.3f}, "
                  f"race {b['race_found'] - base['race_found']:+.3f}")
    print("\nper item: source key class/group, passing lines, on-point, ids, example")
    for r in rows:
        print(f"   {r['source'][-6:]} {r['key']:<4} {r['class']}/{r['why']:<8} "
              f"{'HEDGED ' if r['hedged'] else ''}{r['passing']:>4} {r['on_point']:>4} "
              f"{','.join(r['ids']) or '-'}  {(r['example'] or '')[:90]}")


# ============ score ============

def _bridge_class(label) -> str:
    if label in ("race", "gate"):  # labels.json's valid classes
        return "valid"
    if label in replay.FP_CLASSES:
        return "fp"
    return str(label)


def score(set_name: str) -> dict:
    """Arms A (j8) and B (after repair) on the same replies, and the
    offered items by class, quote group and result."""
    corpus_labels = json.loads(replay.CORPUS_LABELS_PATH.read_text(encoding="utf-8"))
    valid_classes = set(corpus_labels.get("valid", []))
    arms: Dict[str, Dict[str, list]] = {"A": {}, "B": {}}
    offered_rows, calls, missing = [], Counter(), []
    for sample in samples(set_name):
        code_diff = read_input(sample["diff_path"])
        rdiff = replay.load_diff(code_diff, _symbols(sample["index_path"]))
        items = judged_items(sample, rdiff)
        kept = [i for i, reason in items if reason is None]
        path = OUT_DIR / f"measurement_repair_{sample['id']}.json"
        restored_keys = set()
        if path.exists():
            rep = json.loads(path.read_text(encoding="utf-8"))
            calls["calls"] += 1
            calls["skipped"] += bool(rep["skipped"])
            calls["runaways"] += sum(1 for t in rep["telemetry"] if t["outcome"] != "ok")
            label_of = {i.key: i.label for i, _ in items}
            for off, out in zip(rep["offered"], rep["outcomes"]):
                if out.get("restored_blocker"):
                    restored_keys.add(off["key"])
                label = label_of.get(off["key"])
                cls = _item_class(set_name, sample, label, valid_classes)
                offered_rows.append({"source": sample["id"], "key": off["key"],
                                     "class": cls, "label": label, "why": off["why"],
                                     "result": out["result"], "blocker": off["blocker"],
                                     "restored": out.get("restored_blocker")})
        else:
            # nothing offered: either no quote failures, or the run is missing
            if any(reason == "evidence" and _evidence(i) for i, reason in items):
                missing.append(sample["id"])
        group = sample["fixture"]["id"] if sample["fixture"] else "bridge"
        arms["A"].setdefault(group, []).append(kept)
        arms["B"].setdefault(group, []).append(
            kept + [i for i, _ in items if i.key in restored_keys])

    return {"set": set_name, "calls": dict(calls), "missing": missing,
            "offered": offered_rows, "arms": _pool_arms(set_name, arms)}


def _pool_arms(set_name: str, arms: Dict[str, Dict[str, list]]) -> dict:
    """Each arm's pooled numbers from its kept items per review, grouped
    by fixture (corpus) or under 'bridge'."""
    corpus_labels = json.loads(replay.CORPUS_LABELS_PATH.read_text(encoding="utf-8"))
    valid_classes = set(corpus_labels.get("valid", []))
    manifest_fixtures, out = {}, {}
    if set_name == "corpus":
        from eval_harness.corpus import load_manifest
        manifest_fixtures = {f["id"]: f for f in load_manifest()["fixtures"]}
    for arm, groups in arms.items():
        if set_name == "corpus":
            per = {}
            for fid, runs in groups.items():
                bugs = [b["id"] for b in manifest_fixtures[fid]["known_bugs"]]
                per[fid] = replay.summarize_corpus(
                    [replay.corpus_stats(k, set(bugs), valid_classes) for k in runs], bugs)
            kinds = {fid: manifest_fixtures[fid]["kind"] for fid in per}
            out[arm] = replay.pool_corpus(per, kinds)
        else:
            out[arm] = replay.summarize([replay.review_stats(k) for k in groups["bridge"]])
    return out


def _item_class(set_name: str, sample: dict, label, valid_classes: set) -> str:
    if set_name == "corpus":
        bugs = {b["id"] for b in sample["fixture"]["known_bugs"]}
        return "valid" if set(label or []) & (bugs | valid_classes) else "fp"
    return _bridge_class(label)


def print_score(res: dict) -> None:
    print(f"set: {res['set']}; repair calls {res['calls'].get('calls', 0)}, "
          f"skipped {res['calls'].get('skipped', 0)}, "
          f"attempts not ok {res['calls'].get('runaways', 0)}")
    for sid in res["missing"]:
        print(f"MISSING repair run for {sid}")
    for arm in ("A", "B"):
        a = res["arms"][arm]
        print(f"arm {arm}: " + ", ".join(
            f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}" for k, v in a.items()))
    a, b = res["arms"]["A"], res["arms"]["B"]
    if res["set"] == "corpus":
        print(f"delta: recall {b['mean_recall'] - a['mean_recall']:+.3f}, "
              f"FPs per review {b['fp_per_review'] - a['fp_per_review']:+.3f}")
    else:
        print(f"delta: FPs per review {b['fp_per_review'] - a['fp_per_review']:+.3f}, "
              f"race {b['race_found'] - a['race_found']:+.3f}, "
              f"gate {b['gate_found'] - a['gate_found']:+.3f}")
    print("\noffered items by class, quote group, result:")
    counts = Counter((r["class"], r["why"], r["result"]) for r in res["offered"])
    for (cls, why, result), n in sorted(counts.items()):
        print(f"   {cls:<12} {why:<8} {result:<13} {n}")
    restored_fp = [r for r in res["offered"] if r["restored"] and r["class"] != "valid"]
    if restored_fp:
        print("\nrestored items that are not valid:")
        for r in restored_fp:
            print(f"   {r['source']} {r['key']} [{r['label']}] {r['restored'][:200]}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="The repair pass, paired on "
                                                 "archived round-1 replies")
    parser.add_argument("command", choices=("run", "score", "ceiling"))
    parser.add_argument("--set", choices=tuple(SETS), required=True)
    parser.add_argument("--dry", action="store_true",
                        help="With run: list the offers, call nothing")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "run":
        run(args.set, args.dry)
    elif args.command == "ceiling":
        print_ceiling(ceiling(args.set))
    else:
        print_score(score(args.set))


if __name__ == "__main__":
    main()
