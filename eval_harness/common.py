"""common.py — what the round-1 and round-2 measurement scripts share:
the command line, collecting samples, reading inputs and records, and
the scoring helpers (attempt status, demoted blockers, M1, M2
candidates)."""

import argparse
import contextlib
import functools
import glob
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

from retrieval import IDENT, code_like


# ============ inputs and records ============

def read_input(path: str) -> str:
    """Read as orchestrator.py does, so the diff hashes match the records."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SystemExit(f"ERROR: cannot read {path}: {exc}")


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


# ============ scoring helpers ============

# Where a field starts in a flattened {claim, file, quote} blocker
# (adjudication._coerce_item joins "key: value" pairs with "; ").
_FIELD = re.compile(r"(?:^|; )(claim|file|quote): ")


def parse_blocker(item: str) -> dict:
    """A stored reviewer blocker back as its fields: claim, file and quote,
    plus hedge_text, the blocker without its quote, which is what the hedge
    check reads (adjudication._evidence). A plain string is all claim."""
    marks = list(_FIELD.finditer(item))
    if not marks:
        return {"claim": item, "file": "", "quote": "", "hedge_text": item}
    fields, quote_span = {}, None
    for m, nxt in zip(marks, marks[1:] + [None]):
        end = nxt.start() if nxt else len(item)
        fields[m.group(1)] = item[m.end():end]
        if m.group(1) == "quote":
            quote_span = (m.start(), end)
    hedge_text = item
    if quote_span:
        hedge_text = (item[:quote_span[0]] + item[quote_span[1]:]).lstrip("; ")
    return {"claim": fields.get("claim", ""), "file": fields.get("file", ""),
            "quote": fields.get("quote", ""), "hedge_text": hedge_text}


def claim_text(item: str) -> str:
    """The claim of a flattened {claim, file, quote} blocker; a plain
    string is all claim."""
    return parse_blocker(item)["claim"] or item


def reviewer_status(entry: dict) -> str:
    """How a round entry's reviewer reply was obtained: 'first', 'retry'
    or 'failed'. 'unknown' for records without telemetry (before v5.2)."""
    if entry["reviewer"].get("verdict") == "PARSE_FAILURE":
        return "failed"
    calls = (entry.get("telemetry") or {}).get("reviewer")
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
    names = set(IDENT.findall(blocker)) & removed
    return sorted(n for n in names if code_like(n) and lacks(n))


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


# ============ run ============

def collect(measure: Callable[..., dict], summary: Callable[[dict], str],
            models: str, proposal: str, code_diff: str, code_context: str,
            header: bool, runs: int, index_path: Optional[str] = None) -> None:
    """Take runs samples with measure (debate.run_round1_review or
    run_round2_pair), printing each record's path, summary(result) and
    any agent failures. Stops when the input is refused, since every run
    would be, or when a request failed, since an unreachable server would
    only fill coach_artifacts/ with failure records. A runaway that
    exhausts its retries is a result worth keeping."""
    # index_path is passed only when given, so measures without the
    # parameter (and the tests' fakes) keep working.
    kwargs = {"index_path": index_path} if index_path else {}
    for i in range(1, runs + 1):
        started = time.monotonic()
        res = measure(proposal, code_diff, code_context, header_artifact=header,
                      **kwargs)
        print(f"[{i}/{runs}] {res['record_path']}: {summary(res)}, "
              f"{(time.monotonic() - started) / 60:.1f} min")
        failures = res.get("agent_failures", [])
        for failure in failures:
            print(f"    {failure}")
        if "input_refused" in res:
            raise SystemExit(f"Stopping: input refused: {res['input_refused']}")
        if any("request failed" in f for f in failures):
            raise SystemExit("Stopping: the Ollama request failed. Is the "
                             f"server up and {models} pulled?")


@contextlib.contextmanager
def agent_model(role: str, model: Optional[str]) -> Iterator[str]:
    """Sample with another model for one role, 'code_reviewer' or
    'auto_engineer' (the bake-offs, ADR-0002): sets config.MODELS[role],
    which debate.py reads and every record stamps under models_used, and
    restores it on exit. None keeps the configured model."""
    from config import MODELS
    old = MODELS[role]
    MODELS[role] = model or old
    try:
        yield MODELS[role]
    finally:
        MODELS[role] = old


# ============ command line ============

def main(name: str, measure: Callable[..., dict], summary: Callable[[dict], str],
         models: str, score: Callable, report: Callable, score_help: str,
         records_help: str) -> None:
    """A measurement script's command line: `run` collects samples with
    measure; `score` prints report(score(records, diff, symbols, lacks),
    symbols, m2_on). name is the measurement, e.g. 'round-1 reviewer'."""
    parser = argparse.ArgumentParser(
        description=f"{name[0].upper()}{name[1:]} measurements: collect and "
                    "score samples")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help=f"Collect {name} samples")
    run_p.add_argument("--proposal", required=True)
    run_p.add_argument("--diff", help="Path to the code diff")
    run_p.add_argument("--context", help="Path to surrounding code context")
    run_p.add_argument("--header", action="store_true",
                       help="Review target is header-only (C ABI stub)")
    run_p.add_argument("--runs", type=int, default=1)
    run_p.add_argument("--index-file", metavar="PATH",
                       help="Repo context index to retrieve from, instead of "
                            "repo_context.json (a corpus fixture's own)")
    run_p.add_argument("--reviewer-model", metavar="NAME",
                       help="An Ollama model to review with instead of "
                            "config.MODELS['code_reviewer']")

    score_p = sub.add_parser("score", help=score_help)
    score_p.add_argument("records", nargs="+", metavar="RECORD", help=records_help)
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
        with agent_model("code_reviewer", args.reviewer_model) as model:
            collect(measure, summary, model if args.reviewer_model else models,
                    args.proposal, read_input(args.diff) if args.diff else "",
                    read_input(args.context) if args.context else "",
                    args.header, args.runs, args.index_file)
        return
    if bool(args.repo) != bool(args.rev):
        parser.error("--repo and --rev go together")
    # Blocker text is model output; redirected to a file on Windows the
    # default cp1252 would crash on the first arrow or math sign.
    sys.stdout.reconfigure(encoding="utf-8")
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    lacks = post_state_lacks(args.repo, args.rev) if args.repo else None
    report(score(load_records(args.records), read_input(args.diff), symbols, lacks),
           symbols, m2_on=lacks is not None)
