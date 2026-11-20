"""The twenty-sixth measurement (ADR-0002): other reviewers' findings
under verify_findings, on corpus v2.

Each review is one record, coach_artifacts/measurement_outside_<id>.json:
the reviewer (C, the hand-written control; S, a hosted model; L, a local
one), the arm (N, native prose converted by the fixed rule here; Q, the
quoted JSON shape), the fixture, the raw reply and the findings taken
from it. No record holds an outcome: `score` computes them, and only
once every finding is labeled (eval_harness/outside_labels.json).

    python -m eval_harness.outside lines --fixture loader_count_0b43261
    python -m eval_harness.outside prompt --fixture all --arm both --out <dir>
    python -m eval_harness.outside ingest --reviewer S --model <id> \\
        --fixture loader_count_0b43261 --arm N reply.txt
    python -m eval_harness.outside control
    python -m eval_harness.outside run --fixture all --arm both --runs 3 --model gpt-oss:20b
    python -m eval_harness.outside list "coach_artifacts/measurement_outside_*.json"
    python -m eval_harness.outside score "coach_artifacts/measurement_outside_*.json"

`run` calls a local model on Ollama through raw_call.chat and holds the
GPU; every other command makes no model call.
"""

import argparse
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import adjudication
from debate import text_sha256
from diff_reader import read_diff, diff_paths
from eval_harness import raw_call
from eval_harness.common import load_records
from eval_harness.corpus import LABELS_PATH as CORPUS_LABELS_PATH
from eval_harness.corpus import MANIFEST_V2, load_manifest, select

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDS_DIR = REPO_ROOT / "coach_artifacts"
LABELS_PATH = Path(__file__).with_name("outside_labels.json")
CONTROL_PATH = Path(__file__).with_name("outside_control.json")
MODE = "outside_findings"
REVIEWERS = ("C", "S", "L")
ARMS = ("N", "Q")
CONVERSION = "n1"  # arm N's rule as registered; a change gets a new name

# The arms' prompts, verbatim from ADR-0002's twenty-sixth measurement
PROMPTS = {
    "N": (
        "You are reviewing a pull request. Its description and its unified diff follow.\n"
        "Report each problem you find in the changed code: bugs, races, missing checks,\n"
        "wrong behavior. Number the findings. For each, give the file and the line, and\n"
        "explain the problem. If you find none, reply \"No findings.\""),
    "Q": (
        "You are reviewing a pull request. Its description and its unified diff follow.\n"
        "Report each problem you find in the changed code: bugs, races, missing checks,\n"
        "wrong behavior. Reply with JSON only, in this form:\n"
        "{\"findings\": [{\"claim\": \"...\", \"file\": \"...\", \"quote\": \"...\"}]}\n"
        "claim: the problem, stated plainly. file: the path of the file it is in.\n"
        "quote: the code the claim rests on, copied verbatim from the post-change side\n"
        "of the diff (a context or added line, without its leading \"+\" or space).\n"
        "Reply {\"findings\": []} if you find none."),
}
# What S is told before the prompt (ADR-0002, the measurement's implementation note)
NO_TOOLS = "Answer from the text below alone: use no tools and read no files."


# Fixtures and requests

def fixtures(ids: List[str]) -> List[dict]:
    return select(load_manifest(MANIFEST_V2), ids)


def fixture_by_id(fixture_id: str) -> dict:
    [fixture] = fixtures([fixture_id])
    return fixture


def diff_text(fixture: dict) -> str:
    return fixture["diff_path"].read_text(encoding="utf-8")


def user_text(fixture: dict) -> str:
    return f"Description:\n{fixture['proposal']}\n\nDiff:\n{diff_text(fixture)}"


def hosted_prompt(fixture: dict, arm: str) -> str:
    """The one message S receives."""
    return f"{NO_TOOLS}\n\n{PROMPTS[arm]}\n\n{user_text(fixture)}"


def post_lines(code_diff: str) -> List[Tuple[str, int, str, str]]:
    """Every post-change line of the diff as (path, line number, tag, text):
    context (' ') and added ('+') lines, numbered as the file reads after
    the change, from each hunk header's '+start'."""
    out, path, number = [], None, 0
    starts = iter(int(m.group(1)) for m in re.finditer(
        r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", code_diff, re.M))
    for tag, text in read_diff(code_diff):
        if tag == "+++":
            path = text
        elif tag == "@@":
            number = next(starts)
        elif tag in (" ", "+") and path is not None:
            out.append((path, number, tag, text))
            number += 1
    return out


# Arm N: native prose to findings (rule n1)

_ITEM = re.compile(r"^[ \t#*]*\d+[.)][ \t]")
_FENCE_LINE = re.compile(r"^\s*(```|~~~)")
_FENCED = re.compile(r"^\s*(?:```|~~~)[^\n]*\n(.*?)^\s*(?:```|~~~)[ \t]*$", re.S | re.M)
_SPAN = re.compile(r"`([^`\n]+)`")
_PATH = re.compile(r"[\w./-]+\.\w+")
_LINE_CITE = re.compile(r"[\w./-]+\.\w+:\d+|\blines?\s+\d+", re.I)


def split_findings(reply: str) -> List[str]:
    """The reply's findings: each starts at a line beginning with a number
    and '.' or ')' (after any '#', '*' or spaces) outside a code fence;
    text before the first is dropped."""
    items: List[List[str]] = []
    fenced = False
    for line in reply.splitlines():
        if not fenced and _ITEM.match(line):
            items.append([line])
        elif items:
            items[-1].append(line)
        if _FENCE_LINE.match(line):
            fenced = not fenced
    return ["\n".join(lines).strip() for lines in items]


def _quote_of(finding: str) -> str:
    block = _FENCED.search(finding)
    if block and block.group(1).strip():
        return block.group(1).strip("\n")
    spans = [s for s in _SPAN.findall(finding) if len(s.replace(" ", "")) >= 8]
    return max(spans, key=len) if spans else ""


def _file_of(finding: str, paths: List[str]) -> str:
    for token in _PATH.findall(finding.replace("`", " ")):
        token = re.sub(r"^[ab]/", "", token)
        if token in paths:
            return token
        hits = [p for p in paths if p.endswith("/" + token)]
        if len(hits) == 1:
            return hits[0]
    return ""


def convert_native(reply: str, code_diff: str) -> List[dict]:
    """Arm N's findings as {claim, file, quote, cites_line} (rule n1)."""
    paths = diff_paths(code_diff)
    out = []
    for finding in split_findings(reply):
        out.append({"claim": _FENCED.sub("", finding).strip(),
                    "file": _file_of(finding, paths),
                    "quote": _quote_of(finding),
                    "cites_line": bool(_LINE_CITE.search(finding))})
    return out


# Arm Q: the quoted JSON shape

def parse_quoted(reply: str) -> Tuple[Optional[List[dict]], Optional[str]]:
    """(findings, None), or (None, why the reply is unusable). One fence
    around the whole reply is removed first."""
    text = reply.strip()
    fence = re.fullmatch(r"(?:```|~~~)[\w-]*\n(.*)\n(?:```|~~~)", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None, "not JSON"
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return None, "not a JSON object with a findings list"
    out = []
    for item in data["findings"]:
        if isinstance(item, dict):
            out.append({k: "" if item.get(k) is None else str(item[k])
                        for k in adjudication.FINDING_FIELDS})
        else:
            out.append({"claim": str(item), "file": "", "quote": ""})
    return out, None


def findings_of(reply: str, arm: str, code_diff: str, call: Optional[dict] = None
                ) -> Tuple[List[dict], Optional[str]]:
    """(findings, unusable reason or None) for one reply."""
    if call and call.get("error"):
        return [], call["error"]
    if call and call.get("done_reason") == "length":
        return [], "hit the output cap"
    if not reply.strip():
        return [], "empty reply"
    if arm == "N":
        return convert_native(reply, code_diff), None
    found, reason = parse_quoted(reply)
    return (found or []), reason


# Records

def new_id() -> str:
    return (f"outside_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_"
            f"{secrets.token_hex(3)}")


def make_record(reviewer: str, model: str, arm: str, fixture: dict, reply: str,
                call: Optional[dict] = None, prompt: str = "") -> dict:
    code_diff = diff_text(fixture)
    found, reason = findings_of(reply, arm, code_diff, call)
    record_id = new_id()
    return {
        "metadata": {"mode": MODE, "measurement": "twenty-sixth", "id": record_id,
                     "created_utc": datetime.now(timezone.utc).isoformat(),
                     "reviewer": reviewer, "model": model, "arm": arm,
                     "fixture": fixture["id"], "manifest": "docs/fixtures/corpus_v2.json",
                     "conversion": CONVERSION if arm == "N" else None,
                     "prompt_sha256": text_sha256(prompt) if prompt else None,
                     "settings": dict(raw_call.CHAT_OPTIONS) if reviewer == "L" else None},
        "inputs": {"diff_sha256": text_sha256(code_diff), "proposal": fixture["proposal"]},
        "outputs": {"reply": reply, "usable": reason is None, "unusable_reason": reason,
                    "findings": found, "call": call},
    }


def save(record: dict, out_dir: Path = RECORDS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"measurement_{record['metadata']['id']}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def control_records() -> List[dict]:
    """The control's records, one per bug fixture and arm. Each Q finding's
    'bug' (its label) is dropped from what is judged."""
    control = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
    out = []
    for fixture_id, arms in control["fixtures"].items():
        fixture = fixture_by_id(fixture_id)
        for arm in ARMS:
            reply = arms[arm] if arm == "N" else json.dumps(
                {"findings": [{k: f[k] for k in adjudication.FINDING_FIELDS if k in f}
                              for f in arms["Q"]["findings"]]}, indent=2, ensure_ascii=False)
            out.append(make_record("C", "hand-written", arm, fixture, reply))
    return out


# Scoring

def _valid_terms(labels: dict) -> set:
    corpus = json.loads(CORPUS_LABELS_PATH.read_text(encoding="utf-8"))
    return set(corpus["valid"]) | set(labels.get("valid") or [])


def judged(records: List[tuple], labels: dict) -> List[dict]:
    """One row per finding: its record's reviewer, arm and fixture, its
    labels, whether it is valid, its outcome and its citation kind.
    Refuses when any finding is unlabeled."""
    valid_terms = _valid_terms(labels)
    by_record = labels.get("records") or {}
    rows, missing = [], []
    for _, rec in records:
        meta, out = rec["metadata"], rec["outputs"]
        fixture = fixture_by_id(meta["fixture"])
        known = {b["id"] for b in fixture.get("known_bugs", [])}
        code_diff = diff_text(fixture)
        symbols = adjudication.index_symbols(
            json.loads(fixture["index_path"].read_text(encoding="utf-8")))
        results = adjudication.verify_findings(out["findings"], code_diff, "", symbols)
        marks = (by_record.get(meta["id"]) or {}).get("labels") or {}
        for i, (finding, result) in enumerate(zip(out["findings"], results), 1):
            key = f"#{i}"
            if key not in marks:
                missing.append(f"{meta['id']} {key}")
                continue
            terms = marks[key]
            rows.append({"reviewer": meta["reviewer"], "arm": meta["arm"],
                         "fixture": meta["fixture"], "record": meta["id"], "key": key,
                         "labels": terms, "bugs": [t for t in terms if t in known],
                         "valid": any(t in known or t in valid_terms for t in terms),
                         "outcome": result["outcome"],
                         "citation": ("quote" if finding.get("quote") else
                                      "line" if finding.get("cites_line") else "neither")})
    if missing:
        raise SystemExit("ERROR: unlabeled findings, label them before scoring:\n  "
                         + "\n  ".join(missing))
    return rows


def _share(n: int, d: int) -> Optional[float]:
    return round(n / d, 3) if d else None


def measures(rows: List[dict], records: List[tuple], reviewer: str, arm: str) -> dict:
    """The registered measures for one reviewer and arm."""
    recs = [r for _, r in records
            if r["metadata"]["reviewer"] == reviewer and r["metadata"]["arm"] == arm]
    usable = [r for r in recs if r["outputs"]["usable"]]
    mine = [x for x in rows if x["reviewer"] == reviewer and x["arm"] == arm]
    kept = [x for x in mine if x["outcome"] == adjudication.KEPT]
    valid = [x for x in mine if x["valid"]]
    false = [x for x in mine if not x["valid"]]
    k_v = _share(sum(x["outcome"] == adjudication.KEPT for x in valid), len(valid))
    k_f = _share(sum(x["outcome"] == adjudication.KEPT for x in false), len(false))
    manifest = load_manifest(MANIFEST_V2)
    recall_all, recall_kept = [], []
    for fixture in manifest["fixtures"]:
        runs = [r["metadata"]["id"] for r in usable if r["metadata"]["fixture"] == fixture["id"]]
        for bug in fixture.get("known_bugs", []):
            if not runs:
                continue
            hit = lambda pool: sum(any(bug["id"] in x["bugs"] for x in pool
                                       if x["record"] == run) for run in runs) / len(runs)
            recall_all.append(hit(mine))
            recall_kept.append(hit(kept))
    clean = {f["id"] for f in manifest["fixtures"] if f["kind"] == "clean"}
    clean_runs = [r for r in usable if r["metadata"]["fixture"] in clean]
    clean_false = [x for x in false if x["fixture"] in clean]
    outcomes = {}
    for x in mine:
        key = "valid" if x["valid"] else "false"
        outcomes.setdefault(key, {}).setdefault(x["outcome"], 0)
        outcomes[key][x["outcome"]] += 1
    citations = {}
    if arm == "N":
        for x in mine:
            key = f"{'valid' if x['valid'] else 'false'} {x['citation']}"
            citations.setdefault(key, {}).setdefault(x["outcome"], 0)
            citations[key][x["outcome"]] += 1
    p_all = _share(len(valid), len(mine))
    p_kept = _share(sum(x["valid"] for x in kept), len(kept))
    r_all = round(sum(recall_all) / len(recall_all), 3) if recall_all else None
    r_kept = round(sum(recall_kept) / len(recall_kept), 3) if recall_kept else None
    d = round(k_v - k_f, 3) if k_v is not None and k_f is not None else None
    claim = (p_all is not None and p_kept is not None and d is not None
             and r_all is not None and r_kept is not None
             and p_kept - p_all >= 0.10 and d >= 0.20 and r_kept >= 0.75 * r_all)
    return {"reviewer": reviewer, "arm": arm, "reviews": len(recs), "usable": len(usable),
            "findings": len(mine),
            "findings_per_review": _share(len(mine), len(usable)),
            "P_all": p_all, "P_kept": p_kept, "K_v": k_v, "K_f": k_f, "D": d,
            "R_all": r_all, "R_kept": r_kept,
            "clean_false_per_review": _share(len(clean_false), len(clean_runs)),
            "clean_false_kept_per_review": _share(
                sum(x["outcome"] == adjudication.KEPT for x in clean_false), len(clean_runs)),
            "outcomes": outcomes, "citations": citations, "claim_rule_holds": claim}


def line_trigger(rows: List[dict]) -> dict:
    """Rule 2, pooled over S and L in arm N."""
    pool = [x for x in rows if x["reviewer"] in ("S", "L") and x["arm"] == "N"
            and x["valid"] and x["outcome"] == adjudication.QUOTE]
    line_only = [x for x in pool if x["citation"] == "line"]
    return {"valid_quote_demotions": len(pool), "line_only": len(line_only),
            "fires": len(line_only) >= 10 and 2 * len(line_only) >= len(pool)}


def control_report(rows: List[dict]) -> List[dict]:
    return [{"arm": x["arm"], "fixture": x["fixture"], "bugs": x["bugs"],
             "outcome": x["outcome"]} for x in rows if x["reviewer"] == "C"]


def score(records: List[tuple], labels: dict) -> dict:
    rows = judged(records, labels)
    present = sorted({(r["metadata"]["reviewer"], r["metadata"]["arm"]) for _, r in records})
    return {"judge_version": adjudication.JUDGE_VERSION,
            "measures": [measures(rows, records, rv, arm) for rv, arm in present],
            "control": control_report(rows), "line_trigger": line_trigger(rows)}


# Commands

def _listing(records: List[tuple]) -> None:
    for path, rec in records:
        meta, out = rec["metadata"], rec["outputs"]
        print(f"== {meta['id']} {meta['reviewer']} {meta['arm']} {meta['fixture']}"
              + ("" if out["usable"] else f" UNUSABLE: {out['unusable_reason']}"))
        for i, f in enumerate(out["findings"], 1):
            print(f"  #{i} file={f['file'] or '-'} quote={'yes' if f['quote'] else 'no'}")
            print("     " + f["claim"].replace("\n", "\n     ")[:1200])


def _local_run(fixture: dict, arm: str, model: str) -> Path:
    reply, call = raw_call.chat(model, PROMPTS[arm], user_text(fixture), json_mode=arm == "Q")
    rec = make_record("L", model, arm, fixture, reply, call, PROMPTS[arm])
    path = save(rec)
    out = rec["outputs"]
    print(f"  {arm} {fixture['id']}: {len(out['findings'])} findings"
          + ("" if out["usable"] else f", unusable: {out['unusable_reason']}")
          + f" ({call.get('wall_s')} s) -> {path.name}")
    return path


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="The twenty-sixth measurement: other reviewers' findings under "
                    "verify_findings (ADR-0002)")
    sub = parser.add_subparsers(dest="command", required=True)
    lines_p = sub.add_parser("lines", help="A fixture's post-change lines, numbered")
    lines_p.add_argument("--fixture", required=True)
    prompt_p = sub.add_parser("prompt", help="Write the hosted reviewer's messages")
    prompt_p.add_argument("--fixture", action="append", required=True)
    prompt_p.add_argument("--arm", choices=ARMS + ("both",), required=True)
    prompt_p.add_argument("--out", required=True, help="A directory for the message files")
    ingest_p = sub.add_parser("ingest", help="Record saved replies of a hosted reviewer")
    ingest_p.add_argument("--reviewer", choices=("S",), required=True)
    ingest_p.add_argument("--model", required=True)
    ingest_p.add_argument("--fixture", required=True)
    ingest_p.add_argument("--arm", choices=ARMS, required=True)
    ingest_p.add_argument("replies", nargs="+", metavar="REPLY")
    sub.add_parser("control", help="Record the hand-written control")
    run_p = sub.add_parser("run", help="Review with a local model (GPU)")
    run_p.add_argument("--fixture", action="append", required=True)
    run_p.add_argument("--arm", choices=ARMS + ("both",), required=True)
    run_p.add_argument("--runs", type=int, default=1)
    run_p.add_argument("--model", required=True)
    for name in ("list", "score"):
        p = sub.add_parser(name)
        p.add_argument("records", nargs="+", metavar="RECORD")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    if args.command == "lines":
        for path, number, tag, text in post_lines(diff_text(fixture_by_id(args.fixture))):
            print(f"{path}:{number}:{tag}{text}")
    elif args.command == "prompt":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for fixture in fixtures(args.fixture):
            for arm in (ARMS if args.arm == "both" else (args.arm,)):
                target = out / f"{fixture['id']}.{arm}.txt"
                target.write_text(hosted_prompt(fixture, arm), encoding="utf-8")
                print(target)
    elif args.command == "ingest":
        fixture = fixture_by_id(args.fixture)
        for reply_path in args.replies:
            reply = Path(reply_path).read_text(encoding="utf-8")
            rec = make_record("S", args.model, args.arm, fixture, reply,
                              prompt=hosted_prompt(fixture, args.arm))
            print(save(rec))
    elif args.command == "control":
        for rec in control_records():
            print(save(rec))
    elif args.command == "run":
        if args.runs < 1:
            parser.error("--runs must be at least 1")
        for fixture in fixtures(args.fixture):
            for _ in range(args.runs):
                for arm in (ARMS if args.arm == "both" else (args.arm,)):
                    _local_run(fixture, arm, args.model)
    else:
        records = [r for r in load_records(args.records) if r[1]["metadata"].get("mode") == MODE]
        if args.command == "list":
            _listing(records)
        else:
            labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
            print(json.dumps(score(records, labels), indent=2))


if __name__ == "__main__":
    main()
