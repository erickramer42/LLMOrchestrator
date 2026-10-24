"""Deterministic adjudication: schema validation, verdict derivation and
hedge demotion. Pure functions: no I/O, no LLM calls. Fully unit-testable
in CI."""

import re
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from diff_reader import DEV_NULL, IDENT, code_like, read_diff

# Stamped into every decision record: a judge change alters final verdicts
# and round counts without touching any prompt, so the prompt fingerprint
# cannot show it. j1 (until 2026-10-22) also required the engineer to have
# zero concerns and questions. j2 (2026-10-22) did not check that reviewer
# blockers quote their evidence. j3 (ADR-0002 arm G, not shipped) accepted
# quotes from either side of the diff, matched in interleaved order. j4
# (2026-10-22) read only lines inside hunks, so a diff without hunk headers
# had no evidence and every reviewer blocker on it was demoted; it also
# missed file headers that end in a tab and a timestamp. j5 (2026-10-22)
# read both with the shared diff_reader, and its hedge check still read a
# reviewer blocker's quoted code. j6 (2026-10-22) read the blocker without
# its quote, but a diff without file headers gave the evidence check no
# lines, so the reviewer could not block it, and empty or oversized input
# still went to the models. j7 refuses such input, reads lines outside any
# file as evidence for any file, and ignores a reply's own
# blocker_evidence (code review 2026-10-23, findings 13, 16 and 17). j8
# also demotes a blocker whose claim names code identifiers, none of
# which occurs in the hunk its quote comes from (claim-quote linkage;
# ADR-0002, sixteenth measurement).
JUDGE_VERSION = "j8-claim-quote-linkage"


# ============ VERDICTS ============

# Every final verdict a record can carry. Only the first two approve.
APPROVED_FOR_MERGE = "APPROVED_FOR_MERGE"
APPROVED_WITH_OPEN_QUESTIONS = "APPROVED_WITH_OPEN_QUESTIONS"
MAX_ROUNDS_VERDICT = "MAX_ROUNDS_EXCEEDED - MANUAL_REVIEW_REQUIRED"
AGENT_FAILURE_VERDICT = "AGENT_FAILURE - MANUAL_REVIEW_REQUIRED"
# Input refused before any model call (judge j7)
NO_INPUT_VERDICT = "NO_INPUT - MANUAL_REVIEW_REQUIRED"
INPUT_TOO_LARGE_VERDICT = "INPUT_TOO_LARGE - MANUAL_REVIEW_REQUIRED"
# A measurement judges nothing, so its record must never read as a merge
# decision, approving or otherwise.
MEASUREMENT_VERDICT = "NOT_ADJUDICATED - ROUND1_MEASUREMENT"
PAIR_VERDICT = "NOT_ADJUDICATED - ROUND2_PAIR_MEASUREMENT"


# ============ SCHEMA VALIDATION ============

# The arrays the judge reads, per agent role (schemas are defined in the
# prompts in reviewer_prompt.py). A reply missing a required array is a
# schema failure, never "no problems found".
SCHEMA_LISTS = {
    "reviewer": {"required": ("blockers", "questions"), "optional": ("nits",)},
    "engineer": {"required": ("blockers", "concerns", "questions"),
                 "optional": ()},
}

# List items that carry no content ("blockers": ["None"]).
_PLACEHOLDER_ITEMS = {"none", "n/a", "na", "null", "nil", "nothing", "-"}


def _coerce_item(item) -> str:
    """One array entry as text. Models often emit objects such as
    {"line": 4, "rule": "...", "issue": "..."}; every field is kept so
    line citations survive into the text the guardrails and judge read."""
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return "; ".join(f"{k}: {v}" for k, v in item.items()
                         if v not in (None, "")).strip()
    return str(item).strip()


def _evidence(item) -> Optional[dict]:
    """The file and quote of an object blocker, and its claim: every
    field but the quote, as text, which is what the hedge check reads.
    None for a plain string, which carries no checkable evidence."""
    if not isinstance(item, dict):
        return None
    return {"file": str(item.get("file") or ""),
            "quote": str(item.get("quote") or ""),
            "claim": _coerce_item({k: v for k, v in item.items() if k != "quote"}),
            # the claim field alone, which linkage reads (j8)
            "assertion": _coerce_item(item.get("claim") or "")}


def normalize_agent_output(raw, role: str) -> Tuple[Optional[dict], Optional[str]]:
    """Validate a parsed agent reply against its role schema and coerce
    the arrays into lists of non-empty strings.

    For the reviewer, out["blocker_evidence"] holds each blocker's file,
    quote and claim, aligned with out["blockers"], for
    demote_unverified_blockers and then demote_hedged_blockers.

    Returns (normalized, None) on success, or (None, reason) when the reply
    cannot be judged. Callers must treat a reason as a failure (fail closed).
    """
    spec = SCHEMA_LISTS[role]
    if not isinstance(raw, dict):
        return None, f"reply is a JSON {type(raw).__name__}, expected an object"
    missing = [k for k in spec["required"] if k not in raw]
    if missing:
        return None, f"missing required keys: {', '.join(missing)}"

    out = dict(raw)
    # Only normalization writes blocker_evidence; one the model supplied
    # would steer the guardrails (judge j7).
    out.pop("blocker_evidence", None)
    for key in spec["required"] + spec["optional"]:
        if key not in out:
            continue
        value = out[key]
        if value is None:
            value = []
        elif isinstance(value, (str, dict)):
            value = [value]
        elif not isinstance(value, list):
            return None, f"'{key}' is a {type(value).__name__}, expected a list"
        kept = [(s, v) for s, v in ((_coerce_item(v), v) for v in value)
                if s and s.lower().strip(" .") not in _PLACEHOLDER_ITEMS]
        out[key] = [s for s, _ in kept]
        if role == "reviewer" and key == "blockers":
            out["blocker_evidence"] = [_evidence(v) for _, v in kept]
    return out, None


# ============ VERDICT DERIVATION ============

def derive_verdict(agent_out: dict, concern_key: str = "questions") -> str:
    """Merge decision from agent CONTENT, never the model's self-reported label.
    concern_key: 'questions' (reviewer) or 'concerns'/'questions' (engineer).
    Anything that is not a well-formed reply fails closed to 'reject'."""
    if (not isinstance(agent_out, dict) or not agent_out
            or agent_out.get("verdict") == "PARSE_FAILURE"):
        return "reject"
    blockers = agent_out.get("blockers")
    if not isinstance(blockers, list):
        return "reject"  # missing/garbled blockers array: unjudgeable
    open_items = (agent_out.get(concern_key, []) or
                  agent_out.get("questions", []) or [])
    if blockers:
        return "reject"
    if open_items:
        return "conditional"
    return "approve"


def convergence_verdict(reviewer_v: str, engineer_v: str) -> Optional[str]:
    """Final verdict if this round settles the debate, else None.
    Takes derive_verdict() results. Converges once neither agent holds a
    blocker; open questions and concerns are carried in the verdict
    instead of forcing another round (backlog #2, minimal rule). Agent
    failures are handled before this is called."""
    if reviewer_v == "reject" or engineer_v == "reject":
        return None
    if reviewer_v == "approve" and engineer_v == "approve":
        return APPROVED_FOR_MERGE
    return APPROVED_WITH_OPEN_QUESTIONS


# ============ HEDGE LANGUAGE DEMOTION ============

HEDGE_PATTERNS = re.compile(
    r"\b(may|might|could|possibly|potentially|speculative|"
    r"needs? verification|unverifiable|suspected|appears to|"
    r"seems to|likely|uncertain|check if|need to confirm|is it|"
    r"doesn't appear to|risk of)\b",
    re.IGNORECASE)


def demote_hedged_blockers(agent_out: dict,
                           concern_key: str = "questions") -> Tuple[dict, int]:
    """Guardrail: speculative/hedged text in blockers becomes a question.
    Enforces the taxonomy rule: a blocker must be a DEMONSTRABLE violation.
    A reviewer blocker is read without its quote (judge j6): hedge words
    in quoted code are the code's, not the reviewer's. Consumes
    blocker_evidence, the last guardrail to read it.
    Returns (output, number of blockers demoted). Demoted blockers are
    appended to the end of concern_key, in their original order."""
    if (not isinstance(agent_out, dict) or not agent_out
            or agent_out.get("verdict") == "PARSE_FAILURE"):
        return agent_out, 0

    out = dict(agent_out)
    evidence = out.pop("blocker_evidence", None) or []
    kept, demoted = [], []

    for i, b in enumerate(out.get("blockers", []) or []):
        ev = evidence[i] if i < len(evidence) else None
        if HEDGE_PATTERNS.search(ev["claim"] if ev else str(b)):
            demoted.append(b)
        else:
            kept.append(b)

    if demoted:
        out["blockers"] = kept
        out[concern_key] = (out.get(concern_key, []) or []) + demoted

    return out, len(demoted)


# ============ EVIDENCE QUOTES (judge j4, ADR-0002 arms G and G3) ============

# A supplied code context accepts a quote whatever file the blocker names,
# and so do diff lines under no file header (judge j7), since no path can
# name them.
CONTEXT_SOURCE = "<code context>"
UNFILED_SOURCE = "<diff lines outside any file>"
_ANY_FILE_SOURCES = (CONTEXT_SOURCE, UNFILED_SOURCE)
MIN_QUOTE_CHARS = 8  # non-space characters in the longest quote line
# Ends each hunk in a file's lines, so a quote cannot join two hunks.
_HUNK_BREAK = "\x00"

_ELLIPSIS = re.compile(r"\.\.\.|…")
_LINE_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?)+$")


def _squash(text: str) -> str:
    return " ".join(text.split())


def evidence_sources(code_diff: str, code_context: str = "") -> Dict[str, List[str]]:
    """What blocker quotes are checked against: each file's code as it
    reads after the change (context and added lines in order; removed
    lines are not evidence), as non-blank lines with whitespace collapsed,
    keyed by path. A deleted file has no lines. A renamed file's lines are
    under both its paths. Lines before any file header, as in a diff
    without file headers, are under UNFILED_SOURCE. A '+++' header that
    does not follow a '---' starts a new file."""
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
        if tag == "-":
            continue
        line = _HUNK_BREAK if tag == "@@" else text
        for p in paths or [UNFILED_SOURCE]:
            files.setdefault(p, []).append(line)
    sources = {p: [s for s in map(_squash, lines) if s] for p, lines in files.items()}
    if code_context:
        sources[CONTEXT_SOURCE] = [s for s in map(_squash, code_context.split("\n")) if s]
    return sources


def _match_file(name: str, sources: Dict[str, List[str]]) -> Optional[str]:
    """The diff path a blocker's file names: its first token, without
    quotes, an a/ or b/ prefix or a :line suffix; exact, or a unique path
    suffix."""
    tokens = name.strip().strip("`'\"").split()
    if not tokens:
        return None
    n = _LINE_SUFFIX.sub("", re.sub(r"^[ab]/", "", tokens[0].strip("`'\",()")))
    if n in sources and n not in _ANY_FILE_SOURCES:
        return n
    hits = [p for p in sources if p not in _ANY_FILE_SOURCES and p.endswith("/" + n)]
    return hits[0] if len(hits) == 1 else None


def _quote_fragments(quote: str) -> List[List[str]]:
    """The quote split at ellipses into fragments, each a list of its
    non-blank lines without a diff marker, with the surrounding backticks
    or quotes removed and whitespace collapsed."""
    fragments = []
    for part in _ELLIPSIS.split(quote.strip().strip("`'\"")):
        lines = []
        for line in part.split("\n"):
            s = line.strip()
            if s[:1] in ("+", "-") and s[1:2] not in ("+", "-", ">", "="):
                s = s[1:]
            s = _squash(s)
            if s:
                lines.append(s)
        if lines:
            fragments.append(lines)
    return fragments


def _fragment_found(fragment: List[str], source: List[str]) -> bool:
    """Each quote line is a substring of consecutive source lines (so a
    quote may omit a trailing comment), or the joined quote is a substring
    of the joined source (a quote reflowed onto fewer lines). Neither
    crosses a hunk boundary."""
    k = len(fragment)
    if any(all(q in source[j + i] for i, q in enumerate(fragment))
           for j in range(len(source) - k + 1)):
        return True
    return " ".join(fragment) in " ".join(source)


def _fragment_positions(fragment: List[str], source: List[str]) -> Optional[List[int]]:
    """Where _fragment_found finds the fragment: the positions of the
    source lines it matched, or None."""
    k = len(fragment)
    for j in range(len(source) - k + 1):
        if all(q in source[j + i] for i, q in enumerate(fragment)):
            return list(range(j, j + k))
    joined, starts, pos = " ".join(fragment), [], 0
    for line in source:
        starts.append(pos)
        pos += len(line) + 1
    at = " ".join(source).find(joined)
    if at < 0:
        return None
    return [i for i, s in enumerate(starts)
            if s < at + len(joined) and s + len(source[i]) > at]


def quote_location(evidence: Optional[dict], sources: Dict[str, List[str]]
                   ) -> Optional[Tuple[str, List[int]]]:
    """(source key, matched line positions) where _quote_verified finds
    the quote, trying the same sources in the same order; None when it
    does not find it."""
    if not evidence:
        return None
    fragments = _quote_fragments(evidence.get("quote", ""))
    if not fragments or max(len(line.replace(" ", "")) for f in fragments
                            for line in f) < MIN_QUOTE_CHARS:
        return None
    path = _match_file(evidence.get("file", ""), sources)
    for p in ([path] if path else []) + [s for s in _ANY_FILE_SOURCES if s in sources]:
        spots = [_fragment_positions(f, sources[p]) for f in fragments]
        if all(s is not None for s in spots):
            return p, sorted(set().union(*spots))
    return None


# ============ CLAIM-QUOTE LINKAGE (judge j8) ============

# A token of capital letters only (PID, UI): an acronym, not code, unless
# the index of the reviewed repo defines it as a type or constant name.
ACRONYM = re.compile(r"[A-Z]+")


def hunk_identifiers(code_diff: str) -> Dict[str, List[Set[str]]]:
    """Each file's hunks as the identifiers on all their lines: removed
    lines and the hunk header's context included. Hunk i holds the lines
    after the i-th hunk break in the file's evidence source (hunk 0 is
    what precedes the first), and paths are tracked as evidence_sources
    tracks them."""
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


def claim_identifiers(claim: str, symbols: Optional[FrozenSet[str]] = None) -> Set[str]:
    """The code identifiers a claim names. With symbols (the index's type
    and constant names), acronyms are left out unless symbols holds them."""
    ids = {n for n in IDENT.findall(claim) if code_like(n)}
    if symbols is not None:
        ids = {n for n in ids if not ACRONYM.fullmatch(n) or n in symbols}
    return ids


def _quote_linked(evidence: dict, sources: Dict[str, List[str]],
                  hunks: Dict[str, List[Set[str]]], symbols: FrozenSet[str]) -> bool:
    """Whether a verified blocker's claim names an identifier of the hunk
    its quote comes from. A claim naming no code identifier passes, and so
    does a quote from a source without hunks (a supplied context)."""
    where = quote_location(evidence, sources)
    if where is None:
        return True
    ids = claim_identifiers(evidence.get("assertion", ""), symbols)
    path, positions = where
    if not ids or path not in hunks:
        return True
    source = sources[path]
    found = {source[:i].count(_HUNK_BREAK) for i in positions}
    return bool(ids & set().union(*(hunks[path][h] for h in found if h < len(hunks[path]))))


def _quote_verified(evidence: Optional[dict], sources: Dict[str, List[str]]) -> bool:
    if not evidence:
        return False
    fragments = _quote_fragments(evidence.get("quote", ""))
    if not fragments or max(len(line.replace(" ", "")) for f in fragments
                            for line in f) < MIN_QUOTE_CHARS:
        return False
    texts = []
    path = _match_file(evidence.get("file", ""), sources)
    if path:
        texts.append(sources[path])
    texts += [sources[s] for s in _ANY_FILE_SOURCES if s in sources]
    return any(all(_fragment_found(f, text) for f in fragments) for text in texts)


def demote_unverified_blockers(agent_out: dict, sources: Dict[str, List[str]],
                               concern_key: str = "questions",
                               hunks: Optional[Dict[str, List[Set[str]]]] = None,
                               symbols: FrozenSet[str] = frozenset()) -> Tuple[dict, int]:
    """Guardrail (judge j4): a blocker must quote its evidence from the
    code as it reads after the change. A blocker whose quote is not found
    in the post-change lines of the file it names (or in the supplied
    context, or in diff lines under no file header) moves to the end of
    concern_key, as hedge demotion does.
    With hunks (hunk_identifiers of the diff; judge j8), a blocker whose
    quote is found is demoted the same way when its claim names code
    identifiers and none occurs in the quote's hunk; acronyms count only
    when symbols, the index's type and constant names, holds them.
    Reads blocker_evidence from normalize_agent_output and keeps it
    aligned with the kept blockers, for demote_hedged_blockers.
    Returns (output, number of blockers demoted, for either reason)."""
    if (not isinstance(agent_out, dict) or not agent_out
            or agent_out.get("verdict") == "PARSE_FAILURE"):
        return agent_out, 0

    out = dict(agent_out)
    evidence = out.get("blocker_evidence") or []
    kept, kept_evidence, demoted = [], [], []
    for i, b in enumerate(out.get("blockers", []) or []):
        ev = evidence[i] if i < len(evidence) else None
        if _quote_verified(ev, sources) and (
                hunks is None or _quote_linked(ev, sources, hunks, symbols)):
            kept.append(b)
            kept_evidence.append(ev)
        else:
            demoted.append(b)

    if demoted:
        out["blockers"] = kept
        out["blocker_evidence"] = kept_evidence
        out[concern_key] = (out.get(concern_key, []) or []) + demoted

    return out, len(demoted)
