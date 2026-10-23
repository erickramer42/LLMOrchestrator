"""Deterministic adjudication: schema validation, verdict derivation and
hedge demotion. Pure functions: no I/O, no LLM calls. Fully unit-testable
in CI."""

import re
from typing import Dict, List, Optional, Tuple

# Stamped into every decision record: a judge change alters final verdicts
# and round counts without touching any prompt, so the prompt fingerprint
# cannot show it. j1 (until 2026-10-22) also required the engineer to have
# zero concerns and questions. j2 (2026-10-22) did not check that reviewer
# blockers quote their evidence. j3 (ADR-0002 arm G, not shipped) accepted
# quotes from either side of the diff, matched in interleaved order.
JUDGE_VERSION = "j4-post-change-quotes"


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
    """The file and quote of an object blocker; None for a plain string,
    which carries no checkable evidence."""
    if not isinstance(item, dict):
        return None
    return {"file": str(item.get("file") or ""),
            "quote": str(item.get("quote") or "")}


def normalize_agent_output(raw, role: str) -> Tuple[Optional[dict], Optional[str]]:
    """Validate a parsed agent reply against its role schema and coerce
    the arrays into lists of non-empty strings.

    For the reviewer, out["blocker_evidence"] holds each blocker's file
    and quote, aligned with out["blockers"], for demote_unverified_blockers.

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
        return "APPROVED_FOR_MERGE"
    return "APPROVED_WITH_OPEN_QUESTIONS"


# ============ HEDGE LANGUAGE DEMOTION ============

HEDGE_PATTERNS = re.compile(
    r"\b(may|might|could|possibly|potentially|speculative|"
    r"needs? verification|unverifiable|suspected|appears to|"
    r"seems to|likely|uncertain|check if|need to confirm|is it|"
    r"doesn't appear to|may cause|risk of|might introduce)\b",
    re.IGNORECASE)


def demote_hedged_blockers(agent_out: dict,
                           concern_key: str = "questions") -> Tuple[dict, int]:
    """Guardrail: speculative/hedged text in blockers becomes a question.
    Enforces the taxonomy rule: a blocker must be a DEMONSTRABLE violation.
    Returns (output, number of blockers demoted). Demoted blockers are
    appended to the end of concern_key, in their original order."""
    if (not isinstance(agent_out, dict) or not agent_out
            or agent_out.get("verdict") == "PARSE_FAILURE"):
        return agent_out, 0

    out = dict(agent_out)
    kept, demoted = [], []

    for b in (out.get("blockers", []) or []):
        if HEDGE_PATTERNS.search(str(b)):
            demoted.append(b)
        else:
            kept.append(b)

    if demoted:
        out["blockers"] = kept
        out[concern_key] = (out.get(concern_key, []) or []) + demoted

    return out, len(demoted)


# ============ EVIDENCE QUOTES (judge j4, ADR-0002 arms G and G3) ============

# A supplied code context accepts a quote whatever file the blocker names.
CONTEXT_SOURCE = "<code context>"
MIN_QUOTE_CHARS = 8  # non-space characters in the longest quote line
# Ends each hunk in a file's lines, so a quote cannot join two hunks.
_HUNK_BREAK = "\x00"

_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
_FILE_HEADER = re.compile(r"^(?:---|\+\+\+) (?:[ab]/)?([^\t]+?)\s*$")
_ELLIPSIS = re.compile(r"\.\.\.|…")
_LINE_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?)+$")


def _squash(text: str) -> str:
    return " ".join(text.split())


def evidence_sources(code_diff: str, code_context: str = "") -> Dict[str, List[str]]:
    """What blocker quotes are checked against: each file's code as it
    reads after the change (context and added lines in order; removed
    lines are not evidence), as non-blank lines with whitespace collapsed,
    keyed by path. A deleted file has no lines. Lines are read by hunk
    length, so a removed line that starts with '--' is not taken for a
    file header."""
    files: Dict[str, List[str]] = {}
    paths: List[str] = []
    old_left = new_left = 0
    for line in code_diff.split("\n"):
        if old_left > 0 or new_left > 0:
            tag = line[:1]
            if tag == "\\":  # "\ No newline at end of file"
                continue
            if tag in (" ", "", "-", "+"):  # "" is a context line stripped of its space
                if tag != "+":
                    old_left -= 1
                if tag != "-":
                    new_left -= 1
                    for p in paths:
                        files[p].append(line[1:])
                continue
            old_left = new_left = 0  # malformed hunk: read the line as a header
        hunk = _HUNK.match(line)
        if hunk:
            old_left = int(hunk.group(1) or 1)
            new_left = int(hunk.group(2) or 1)
            for p in paths:
                files[p].append(_HUNK_BREAK)
            continue
        header = _FILE_HEADER.match(line)
        if header:
            if line.startswith("--- "):
                paths = []
            path = header.group(1)
            if path != "/dev/null" and path not in paths:
                paths.append(path)
                files.setdefault(path, [])
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
    if n in sources and n != CONTEXT_SOURCE:
        return n
    hits = [p for p in sources if p != CONTEXT_SOURCE and p.endswith("/" + n)]
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
    if CONTEXT_SOURCE in sources:
        texts.append(sources[CONTEXT_SOURCE])
    return any(all(_fragment_found(f, text) for f in fragments) for text in texts)


def demote_unverified_blockers(agent_out: dict, sources: Dict[str, List[str]],
                               concern_key: str = "questions") -> Tuple[dict, int]:
    """Guardrail (judge j4): a blocker must quote its evidence from the
    code as it reads after the change. A blocker whose quote is not found
    in the post-change lines of the file it names (or in the supplied
    context) moves to the end of concern_key, as hedge demotion does.
    Consumes blocker_evidence from normalize_agent_output.
    Returns (output, number of blockers demoted)."""
    if (not isinstance(agent_out, dict) or not agent_out
            or agent_out.get("verdict") == "PARSE_FAILURE"):
        return agent_out, 0

    out = dict(agent_out)
    evidence = out.pop("blocker_evidence", None) or []
    kept, demoted = [], []
    for i, b in enumerate(out.get("blockers", []) or []):
        ev = evidence[i] if i < len(evidence) else None
        (kept if _quote_verified(ev, sources) else demoted).append(b)

    if demoted:
        out["blockers"] = kept
        out[concern_key] = (out.get(concern_key, []) or []) + demoted

    return out, len(demoted)
