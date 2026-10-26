"""corpus.py — the stable real-diff corpus (backlog #7): list its fixtures,
collect round-1 reviewer samples on one or all of them, each with the
repo context index of its own base, and score the records against each
fixture's known bugs.

    python -m eval_harness.corpus list
    python -m eval_harness.corpus fields [--text]
    python -m eval_harness.corpus run --fixture backoff_clamp_d1c20c0 --runs 5
    python -m eval_harness.corpus run --fixture all --runs 5
    python -m eval_harness.corpus score "coach_artifacts/measurement_round1_*.json"
    python -m eval_harness.corpus score --labels none "coach_artifacts/..."

The manifest, docs/fixtures/corpus.json, names each fixture's diff, the
index of its base, its proposal (written in the diff's real direction,
backlog #21) and its known bugs, each with the symbols a blocker about it
names. `run` sends the request a debate's round 1 sends, with the
fixture's index in place of repo_context.json (debate.run_round1_review
with index_path), so the records carry the debate's prompt fingerprint.
`score` keeps first attempts on a corpus diff and reports, per fixture,
blockers per run, recall per known bug (runs with a stored blocker whose
claim names one of the bug's symbols), the known bugs found only among
demoted blockers, and the blockers that match no known bug, which are
the false-positive candidates and need triage by hand.

With hand labels (eval_harness/corpus_labels.json, read by default), score
also prints what the labels say, per fixture and pooled: the valid share
of stored blockers, false positives by class, each known bug's recall
among stored blockers and among all items (stored or demoted, what the
reviewer said before the guardrails), and the valid items the guardrails
demoted. Items the labels do not cover are listed, so a new sample is
never scored silently.
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import debate
from config import MODELS
from debate import run_round1_review, text_sha256
from diff_reader import diff_paths
from eval_harness.common import (collect, demoted_tail, load_records, m1_hits,
                                 parse_blocker, read_input, reviewer_status)
from file_metadata import identify_layer

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "docs" / "fixtures" / "corpus.json"
LABELS_PATH = Path(__file__).with_name("corpus_labels.json")


# ============ manifest ============

def load_manifest(path: Path = MANIFEST) -> dict:
    """The corpus manifest. Fixture paths are relative to the repo root."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        fixture["diff_path"] = REPO_ROOT / fixture["diff"]
        fixture["index_path"] = REPO_ROOT / fixture["index"]
    return manifest


def select(manifest: dict, ids: List[str]) -> List[dict]:
    """The fixtures named, or all of them for 'all'."""
    fixtures = manifest["fixtures"]
    if ids == ["all"]:
        return fixtures
    by_id = {f["id"]: f for f in fixtures}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise SystemExit(f"ERROR: no corpus fixture named {', '.join(unknown)}; "
                         f"known: {', '.join(by_id)}")
    return [by_id[i] for i in ids]


def describe(fixture: dict) -> dict:
    """What a review of the fixture would send, without a model: the
    diff's size and files, the layer of its note, the pack retrieved from
    the fixture's index with its base check, and the input check."""
    diff = read_input(str(fixture["diff_path"]))
    setup = debate._prepare(diff, "", False, str(fixture["index_path"]))
    check = debate._input_check(setup, fixture["proposal"], diff, "")
    report = setup.pack_report
    return {
        "id": fixture["id"], "kind": fixture["kind"],
        "diff_chars": len(diff), "files": len(diff_paths(diff)),
        "layer": identify_layer(setup.file_path),
        "pack_chars": len(setup.pack_text),
        "pack_error": report.get("error"),
        "base_mismatched": debate._base_mismatch(report),
        "estimated_tokens": check["estimated_tokens"],
        "token_limit": check["token_limit"],
        "refused": check["verdict"],
        "known_bugs": len(fixture.get("known_bugs", [])),
    }


# The bridge fixture is not in the manifest; `fields` audits it too, with
# the committed index and the proposal its records use.
BRIDGE = {"id": "bridge", "kind": "bug",
          "diff_path": REPO_ROOT / "docs" / "fixtures" / "qttune_bridge_refactor.diff",
          "index_path": REPO_ROOT / "repo_context.json",
          "proposal": "Review: coalesced signal updates with LiveView Page v0.3.0 phase 2"}


def print_field_audit(fixture: dict, text: bool = False) -> None:
    """The pack's FIELD DEFINITIONS AND WRITERS section for one fixture,
    without a model (ADR-0002, twentieth measurement, Step 0): whether it
    is empty, its size, the pack's size, the input check, each member
    use, and each declaration and writer with why it was shown or
    dropped; with text, the section as the model sees it."""
    diff = read_input(str(fixture["diff_path"]))
    setup = debate._prepare(diff, "", False, str(fixture["index_path"]))
    check = debate._input_check(setup, fixture["proposal"], diff, "")
    report = setup.pack_report
    audit = report.get("field_audit") or {"uses": {}, "decls": [], "writers": [], "chars": 0}
    shown = report.get("sections", {}).get("fields", 0)
    print(f"\n=== {fixture['id']}: section {'non-empty' if shown else 'empty'}, "
          f"{audit['chars']} chars; pack {report.get('used', 0)} chars"
          f"{', truncated' if report.get('truncated') else ''}; "
          f"input check {check['estimated_tokens']}/{check['token_limit']}"
          f"{' REFUSED' if check['verdict'] else ''}")
    uses = sorted(audit["uses"].items(), key=lambda kv: (-kv[1], kv[0]))
    print("   member uses: " + (", ".join(f"{n} {c}" for n, c in uses) or "none"))
    for d in audit["decls"]:
        print(f"   decl   {d['owner']}::{d['name']} [{d['file']}:{d['line']}] "
              f"{d['dropped'] or 'shown'}")
    for w in audit["writers"]:
        hits = "; ".join(f"{n} {'/'.join(f)}" for n, f in w["writes"].items())
        state = (f"shown, {w['shown_lines']} of {w['lines']} lines" if not w["dropped"]
                 else w["dropped"])
        print(f"   writer {w['function']} [{w['file']}:{w['line']}-{w['end_line']}] "
              f"writes {hits}: {state}")
    if text:
        start = setup.pack_text.find("--- FIELD DEFINITIONS")
        if start != -1:
            end = setup.pack_text.find("\n--- ", start + 4)
            print(setup.pack_text[start:end if end != -1 else None])


def print_listing(rows: List[dict]) -> None:
    print(f"{'fixture':<26} {'kind':<5} {'chars':>6} {'files':>5} {'layer':<8} "
          f"{'pack':>5} {'tokens':>7} {'bugs':>4}  base check")
    for r in rows:
        base = ("no index" if r["pack_error"] else
                f"mismatch: {', '.join(r['base_mismatched'])}" if r["base_mismatched"]
                else "ok")
        refused = f"  REFUSED: {r['refused']}" if r["refused"] else ""
        print(f"{r['id']:<26} {r['kind']:<5} {r['diff_chars']:>6} {r['files']:>5} "
              f"{r['layer']:<8} {r['pack_chars']:>5} "
              f"{r['estimated_tokens']:>7} {r['known_bugs']:>4}  {base}{refused}")
    if rows:
        print(f"\ninput limit {rows[0]['token_limit']} tokens; "
              "'tokens' is the input check's estimate of the round-1 request")


# ============ score ============

def score_records(records: List[tuple], manifest: dict) -> dict:
    """Per fixture: the first-attempt round-1 records on its diff, each
    with its stored and demoted blockers tagged by the known bugs their
    claim names. Records on no corpus diff, retried or failed records are
    listed as excluded."""
    by_hash: Dict[str, dict] = {}
    for fixture in manifest["fixtures"]:
        by_hash[text_sha256(read_input(str(fixture["diff_path"])))] = fixture
    per_fixture: Dict[str, dict] = {f["id"]: {"fixture": f, "rows": []}
                                    for f in manifest["fixtures"]}
    excluded = []
    for path, rec in records:
        record_id = rec["metadata"]["debate_id"]
        fixture = by_hash.get(rec.get("inputs", {}).get("diff_sha256"))
        if fixture is None:
            excluded.append((record_id, "not a corpus diff"))
            continue
        rounds = rec["outputs"]["round_history"]
        if not rounds:
            excluded.append((record_id, "input refused, no round"))
            continue
        status = reviewer_status(rounds[0])
        if status in ("retry", "failed"):
            excluded.append((record_id, "reviewer failed" if status == "failed"
                             else "round-1 reviewer reply came from a retry"))
            continue
        bugs = fixture.get("known_bugs", [])

        def tag(text: str) -> dict:
            claim = parse_blocker(text)["hedge_text"]  # claim and file, not the quote
            return {"text": text,
                    "bugs": [b["id"] for b in bugs if m1_hits(claim, b["symbols"])]}
        unquoted, hedged = demoted_tail(rounds[0])
        per_fixture[fixture["id"]]["rows"].append({
            "id": record_id, "path": str(path), "status": status,
            "fingerprint": rec["metadata"].get("prompt_fingerprint"),
            "blockers": [tag(str(b)) for b in rounds[0]["reviewer"].get("blockers", []) or []],
            "unquoted": [tag(q) for q in unquoted],
            "hedged": [tag(q) for q in hedged]})
    return {"fixtures": per_fixture, "excluded": excluded}


def _items(row: dict) -> List[Tuple[str, str]]:
    """(key, kind) for every item of a scored row, keyed as the report
    and the labels number them; kind is stored, evidence or hedge."""
    return ([(f"#{i}", "stored") for i in range(1, len(row["blockers"]) + 1)]
            + [(f"#e{i}", "evidence") for i in range(1, len(row["unquoted"]) + 1)]
            + [(f"#h{i}", "hedge") for i in range(1, len(row["hedged"]) + 1)])


def labelled_summary(scores: dict, labels: dict) -> dict:
    """What the hand labels say about the scored rows, per fixture and
    pooled. A label is a list of known-bug ids and classes; an item is
    valid when any of them is a known bug of its fixture or a class in
    labels['valid']. Recall per bug counts runs: among stored blockers,
    and among all items, stored or demoted."""
    valid_classes = set(labels.get("valid", []))
    out, unlabelled = {}, []
    pooled = {"runs": 0, "stored": 0, "valid": 0, "fp": {}, "evidence": 0,
              "hedge": 0, "valid_demoted": 0}
    for fixture_id, entry in scores["fixtures"].items():
        rows = entry["rows"]
        if not rows:
            continue
        bug_ids = [b["id"] for b in entry["fixture"].get("known_bugs", [])]
        f = {"runs": len(rows), "stored": 0, "valid": 0, "fp": {}, "evidence": 0,
             "hedge": 0, "valid_demoted": 0,
             "recall": {b: {"stored": 0, "any": 0} for b in bug_ids}}
        for row in rows:
            rec_labels = (labels["records"].get(row["id"]) or {}).get("labels")
            if rec_labels is None:
                unlabelled.append((row["id"], "record"))
                continue
            found_stored, found_any = set(), set()
            for key, kind in _items(row):
                tags = rec_labels.get(key)
                if tags is None:
                    unlabelled.append((row["id"], key))
                    continue
                bugs = {t for t in tags if t in bug_ids}
                valid = bool(bugs) or any(t in valid_classes for t in tags)
                found_any |= bugs
                if kind == "stored":
                    f["stored"] += 1
                    found_stored |= bugs
                    if valid:
                        f["valid"] += 1
                    else:
                        for t in tags:
                            f["fp"][t] = f["fp"].get(t, 0) + 1
                else:
                    f[kind] += 1
                    f["valid_demoted"] += valid
            for b in found_stored:
                f["recall"][b]["stored"] += 1
            for b in found_any:
                f["recall"][b]["any"] += 1
            extra = set(rec_labels) - {k for k, _ in _items(row)}
            unlabelled += [(row["id"], f"{k} (labelled, no such item)") for k in sorted(extra)]
        out[fixture_id] = f
        for k in ("runs", "stored", "valid", "evidence", "hedge", "valid_demoted"):
            pooled[k] += f[k]
        for t, n in f["fp"].items():
            pooled["fp"][t] = pooled["fp"].get(t, 0) + n
    return {"fixtures": out, "pooled": pooled, "unlabelled": unlabelled}


def print_labelled(summary: dict) -> None:
    print("\n==== hand labels ====")
    print(f"{'fixture':<26} {'runs':>4} {'stored':>6} {'valid':>5} {'FP':>4} "
          f"{'#e':>3} {'#h':>3} {'valid demoted':>13}")
    for fixture_id, f in summary["fixtures"].items():
        fp = f["stored"] - f["valid"]
        print(f"{fixture_id:<26} {f['runs']:>4} {f['stored']:>6} {f['valid']:>5} "
              f"{fp:>4} {f['evidence']:>3} {f['hedge']:>3} {f['valid_demoted']:>13}")
    p = summary["pooled"]
    if p["stored"]:
        print(f"\npooled: {p['valid']}/{p['stored']} stored blockers valid "
              f"({p['valid'] / p['stored']:.0%}); evidence-demoted "
              f"{p['evidence'] / p['runs']:.2f} per run; {p['valid_demoted']} valid "
              f"items demoted")
    if p["fp"]:
        print("false positives by class: " + ", ".join(
            f"{t} {n}" for t, n in sorted(p["fp"].items(), key=lambda x: -x[1])))
    print("\nrecall per known bug, runs: stored / stored or demoted")
    for fixture_id, f in summary["fixtures"].items():
        for bug, r in f["recall"].items():
            print(f"   {fixture_id:<26} {bug:<32} {r['stored']}/{f['runs']} "
                  f"/ {r['any']}/{f['runs']}")
    for record_id, key in summary["unlabelled"]:
        print(f"UNLABELLED {record_id} {key}")


def print_report(scores: dict) -> None:
    for entry in scores["fixtures"].values():
        fixture, rows = entry["fixture"], entry["rows"]
        if not rows:
            continue
        n = len(rows)
        # Fixtures differ in their layer note, which the fingerprint
        # hashes, so only a split within one fixture means mixed arms.
        fingerprints = sorted({str(r["fingerprint"]) for r in rows})
        if len(fingerprints) > 1:
            print(f"\nWARNING: {fixture['id']}'s records span {len(fingerprints)} "
                  f"prompt fingerprints ({', '.join(fingerprints)}); score each "
                  "arm separately")
        stored = sum(len(r["blockers"]) for r in rows)
        unmatched = sum(1 for r in rows for b in r["blockers"] if not b["bugs"])
        print(f"\n== {fixture['id']} ({fixture['kind']}): {n} run(s), "
              f"{stored} stored blockers ({stored / n:.2f} per run), "
              f"{unmatched} matching no known bug"
              + (", all false-positive candidates" if fixture["kind"] == "clean"
                 else ""))
        for bug in fixture.get("known_bugs", []):
            found = sum(1 for r in rows if any(bug["id"] in b["bugs"] for b in r["blockers"]))
            demoted_only = sum(
                1 for r in rows
                if not any(bug["id"] in b["bugs"] for b in r["blockers"])
                and any(bug["id"] in b["bugs"] for b in r["unquoted"] + r["hedged"]))
            print(f"   {bug['id']:<18} found in {found}/{n} run(s)"
                  + (f", demoted only in {demoted_only}" if demoted_only else "")
                  + f": {bug['summary']}")
        for r in rows:
            items = ([(f"#{i}", b) for i, b in enumerate(r["blockers"], 1)]
                     + [(f"#e{i}", b) for i, b in enumerate(r["unquoted"], 1)]
                     + [(f"#h{i}", b) for i, b in enumerate(r["hedged"], 1)])
            for label, b in items:
                tags = f"  [{', '.join(b['bugs'])}]" if b["bugs"] else "  [no known bug]"
                print(f"\n{r['id']} {label}{tags}")
                print(textwrap.fill(b["text"], width=96, initial_indent="    ",
                                    subsequent_indent="    "))
    for record_id, reason in scores["excluded"]:
        print(f"excluded {record_id}: {reason}")
    print("\nA symbol match credits a bug; read the claim before counting it "
          "found. Blockers matching no known bug are false-positive candidates "
          "until triaged.")


# ============ command line ============

def _summary(res: dict) -> str:
    return f"{res['blockers']} blockers, {res['attempts']} attempt(s)"


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="The real-diff corpus: list fixtures, collect round-1 "
                    "samples, score records against the known bugs")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="Each fixture's size, layer, pack and input check")
    fields_p = sub.add_parser("fields", help="Each fixture's field section and its "
                                             "audit, the bridge fixture included")
    fields_p.add_argument("--text", action="store_true",
                          help="Also print each section as the model sees it")
    run_p = sub.add_parser("run", help="Collect round-1 reviewer samples")
    run_p.add_argument("--fixture", action="append", required=True,
                       help="A fixture id, repeatable, or 'all'")
    run_p.add_argument("--runs", type=int, default=1, help="Samples per fixture")
    score_p = sub.add_parser("score", help="Score records against the known bugs")
    score_p.add_argument("records", nargs="+", metavar="RECORD",
                         help="Record paths or globs (expanded here)")
    score_p.add_argument("--labels", default=str(LABELS_PATH),
                         help="Hand labels to score with, or 'none' "
                              "(default: eval_harness/corpus_labels.json)")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    if args.command == "list":
        print_listing([describe(f) for f in manifest["fixtures"]])
        return
    if args.command == "fields":
        sys.stdout.reconfigure(encoding="utf-8")
        for fixture in manifest["fixtures"] + [BRIDGE]:
            print_field_audit(fixture, args.text)
        return
    if args.command == "run":
        if args.runs < 1:
            parser.error("--runs must be at least 1")
        for fixture in select(manifest, args.fixture):
            print(f"== {fixture['id']}: {fixture['proposal']}")
            collect(run_round1_review, _summary, MODELS["code_reviewer"],
                    fixture["proposal"], read_input(str(fixture["diff_path"])), "",
                    False, args.runs, str(fixture["index_path"]))
        return
    sys.stdout.reconfigure(encoding="utf-8")
    scores = score_records(load_records(args.records), manifest)
    print_report(scores)
    if args.labels != "none":
        try:
            labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"ERROR: cannot read labels {args.labels}: {exc}")
        print_labelled(labelled_summary(scores, labels))


if __name__ == "__main__":
    main()
