"""Debate-time retrieval from the repo context index: the context pack
(build_context_pack) that debate.py injects into the transcript, and the
check that the index describes the diff's base.

The index, repo_context.json, is built offline by indexer.py and read
from next to this module, from any working directory. Retrieval needs no
model and no network.

The pack is model-facing: its format, PACK_BUDGET and the limits below
are part of the prompt (see PACK_FORMAT_VERSION).
"""

import re
from pathlib import Path
from typing import List, Tuple

from diff_reader import IDENT, base_blobs, code_like, diff_paths, read_diff

CONTEXT_FILE = "repo_context.json"
# Module-relative, so --index writes and debates read the same file
# regardless of the working directory they run from.
_HERE = Path(__file__).resolve().parent
CONTEXT_PATH = _HERE / CONTEXT_FILE

PACK_BUDGET = 6000

# The connection types the indexer harvests call sites for; a pack line
# always keeps its connection type visible.
QUEUED_CONN_RE = re.compile(r"\bQt::(?:Blocking)?QueuedConnection\b")

# MODEL-FACING: build_context_pack's output format, PACK_BUDGET and the
# limits below are part of the prompt. Bump PACK_FORMAT_VERSION (it feeds
# debate.py's prompt_fingerprint) and PROMPT_VERSION together whenever any
# of them changes what agents see.
PACK_FORMAT_VERSION = "f3-diff-authoritative"

# Presentation limits for model-facing pack lines.
SNIPPET_LIMIT = 300      # one rendered call site
TYPE_DECL_LIMIT = 400    # one compact typedef declaration
PURPOSE_LIMIT = 200      # one file purpose
DOC_LIMIT = 160          # one doc comment
# Entries per pack section.
MAX_FILES = 20
MAX_TYPES = 10
MAX_CONSTANTS = 10
MAX_CALL_SITES = 15
MAX_RELATED_CALL_SITES = 10

# IDENT and code_like live in diff_reader (the judge uses them too) and
# are re-exported from here.


# ============ TEXT HELPERS (shared with indexer.py) ============

def clip(text: str, limit: int) -> str:
    """Shorten text to at most `limit` chars at a word boundary, marking the
    cut with an ellipsis. Text that is exactly `limit` long and does not
    end a sentence is treated as already cut (older indexes truncated
    purposes mid-word at 200)."""
    text = " ".join(text.split())
    cut = len(text) > limit or (len(text) == limit
                                and text[-1] not in ".!?)\"'")
    if not cut:
        return text
    head = text[:limit - 1]
    space = head.rfind(" ")
    if space > limit // 2:
        head = head[:space]
    return head.rstrip(" ,;:-") + "…"


def blank_comments(text: str) -> str:
    """text with every // and /* */ comment replaced by spaces, newlines
    kept, so offsets and line numbers still match the original. String
    and char literals are skipped over, so '//' inside them stays."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j == -1 else j
            out[i:j] = " " * (j - i)
            i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] not in (c, "\n"):
                j += 2 if text[j] == "\\" else 1
            i = j + 1
        else:
            i += 1
    return "".join(out)


# ============ RETRIEVAL ============

def _referenced_identifiers(code_diff: str) -> set:
    """Every identifier token in the diff. Retrieval intersects this set
    with the indexed names, so no naming heuristics are needed: ALL_CAPS
    #defines, k-prefixed constants and snake_case types all match, and
    English words in comments match nothing."""
    return set(IDENT.findall(code_diff))


def removed_identifiers(code_diff: str) -> set:
    """Identifiers that appear only on the diff's removed lines: on no
    added line, unchanged context line or hunk-header context. The diff
    shows no surviving use of them. They may still live in parts of a
    file the diff does not show, so retrieval acts on them only for
    entries that belong to a modified file."""
    removed, kept = set(), set()
    for tag, text in read_diff(code_diff):
        if tag == "-":
            removed |= set(IDENT.findall(text))
        elif tag in (" ", "+", "@@"):
            kept |= set(IDENT.findall(text))
    return removed - kept


def _type_line(t: dict) -> str:
    """One KNOWN TYPES line: the compact, comment-free declaration (member
    types and array sizes included, e.g. 'uint8_t data[64]') plus the doc
    comment above it. Falls back to member names for index entries that
    carry no declaration."""
    decl = " ".join(blank_comments(t.get("decl") or "").split())
    if decl and len(decl) > TYPE_DECL_LIMIT:
        cut = max(decl.rfind(";", 0, TYPE_DECL_LIMIT),
                  decl.rfind(",", 0, TYPE_DECL_LIMIT))
        decl = (decl[:cut + 1] if cut > 0 else decl[:TYPE_DECL_LIMIT]) + " …"
    body = decl or ", ".join(t.get("members", []))
    doc = t.get("doc")
    return (f"{t['name']} ({t.get('kind', '?')}): {body}"
            + (f"  // {clip(doc, DOC_LIMIT)}" if doc else ""))


def _callsite_line(cs: dict) -> str:
    """One call-site line. Current indexes store a rendered call that
    already fits; snippets from older indexes can be long, so clip them
    without ever losing the connection type."""
    snippet = " ".join((cs.get("snippet") or "").split())
    if len(snippet) > SNIPPET_LIMIT:
        found = QUEUED_CONN_RE.search(snippet)
        conn = cs.get("connection") or (found.group(0) if found else "")
        head = clip(snippet, SNIPPET_LIMIT - len(conn) - 1)
        snippet = head if conn in head else f"{head} {conn}"
    doc = cs.get("doc")
    return (f"[{cs['file']}:{cs['line']}] {snippet}"
            + (f"  // {clip(doc, DOC_LIMIT)}" if doc else ""))


def _base_check(code_diff: str, index: dict) -> dict:
    """Whether the index describes the diff's base: for each changed file
    whose blob id both the diff and the index record, does the index hold
    the version the diff starts from? 'mismatched' lists the files where
    it does not; the pack may then describe other code (code review
    2026-10-23, finding 15). Diffs without blob ids, and indexes built
    before blob ids were recorded, check nothing."""
    indexed = {f["path"]: f.get("blob") for f in index.get("files", [])}
    checked = {path: blob for path, blob in base_blobs(code_diff).items()
               if indexed.get(path)}
    return {"checked": len(checked),
            "mismatched": sorted(path for path, blob in checked.items()
                                 if not indexed[path].startswith(blob))}


def build_context_pack(code_diff: str, index: dict,
                       budget: int = PACK_BUDGET) -> Tuple[str, dict]:
    """Retrieve indexed context for a given diff. Returns (context_text,
    pack_report). The pack_report holds the budget accounting, section
    counts (matches in 'sections', lines left after the caps and
    truncation in 'shown'), index version and commit, the base check
    (_base_check) and pack format version for the decision record.
    report['used'] is
    len(context_text): exactly what the model sees, excluding debate.py's
    REPO_CONTEXT_TEMPLATE wrapper. The base check never changes the pack.

    The index is a snapshot that can predate the diff, so the diff wins:
    an entry from a modified file that names an identifier only the
    diff's removed lines use is left out of its section and listed by
    name under OMITTED, and a purpose that mentions one says so
    (code review 2026-10-21, finding 1).

    Sections in priority order (truncation cuts from the end); a section
    with no entries is left out entirely:
    1. Files directly modified (from +++ b/ headers)
    2. Types, then constants, referenced by identifier in the diff
    3. Queued-connection call sites in the modified files
    4. Queued-connection call sites in files that define a referenced type
    5. Omitted entries
    """
    report = {
        "budget": budget,
        "used": 0,
        "sections": {},
        "entries": 0,
        "index_version": index.get("index_version"),
        "index_commit": index.get("source_commit"),
        "format_version": PACK_FORMAT_VERSION,
        "error": None,
    }

    if not index.get("files"):
        report["error"] = "empty or missing index"
        return ("", report)
    report["base_check"] = _base_check(code_diff, index)

    changed = diff_paths(code_diff)
    ref_ids = _referenced_identifiers(code_diff)
    removed = {n for n in removed_identifiers(code_diff) if code_like(n)}
    sections, omitted = [], []

    def add_section(key: str, title: str, entry_lines: List[str]) -> None:
        """Queue a section under its report key; an empty one is left out."""
        if entry_lines:
            sections.append((key, title, entry_lines))

    def removed_in(text: str) -> List[str]:
        """The removed-only code identifiers that text names."""
        return sorted(set(IDENT.findall(text)) & removed)

    # Section 1: Modified files (purpose + layer)
    mod_files = [f for f in index["files"] if f["path"] in changed]
    # Build/docs/CI files only carry a path-derived hint ("Build
    # configuration"): list them in one line instead of one line each.
    meta = [f["path"] for f in mod_files if f.get("layer") == "meta"]
    file_lines = []
    for f in [f for f in mod_files if f.get("layer") != "meta"][:MAX_FILES]:
        purpose = clip(f.get("purpose") or "(no purpose available)",
                        PURPOSE_LIMIT)
        gone = removed_in(purpose)
        if gone:
            purpose += f"  [only on the diff's removed lines: {', '.join(gone)}]"
        file_lines.append(f"[{f['path']}] ({f.get('layer') or 'unknown'}): "
                          + purpose)
    if meta:
        file_lines.append("Also modified (build/docs/CI, no summary): "
                          + ", ".join(meta))
    add_section("modified_files", "MODIFIED FILES (machine-written summaries "
                "of the indexed version)", file_lines)

    # Section 2: Referenced types/constants; ones the diff removes from a
    # modified file are omitted
    type_hits, const_hits = [], []
    for t in index.get("types", []):
        if t["name"] not in ref_ids:
            continue
        if t.get("def_file") in changed and t["name"] in removed:
            omitted.append(f"{t['name']} (type, {t['def_file']})")
        else:
            type_hits.append(t)
    for c in index.get("constants", []):
        if c["name"] not in ref_ids:
            continue
        if c["file"] in changed and c["name"] in removed:
            omitted.append(f"{c['name']} (constant, {c['file']})")
        else:
            const_hits.append(c)
    add_section("types", "KNOWN TYPES",
                [_type_line(t) for t in type_hits[:MAX_TYPES]])
    add_section("constants", "CONSTANTS",
                [f"{c['name']} = {c['value']} ({c['kind']})"
                 for c in const_hits[:MAX_CONSTANTS]])

    # Section 3: Queued-connection call sites in the modified files
    all_sites = index.get("callsites", [])
    call_sites = []
    for cs in all_sites:
        if cs["file"] not in changed:
            continue
        gone = removed_in(cs.get("snippet") or "")
        if gone:
            omitted.append(f"queued call site in {cs['file']} using "
                           + ", ".join(gone))
        else:
            call_sites.append(cs)
    add_section("call_sites", "QUEUED CONNECTION CALL SITES (indexed line numbers)",
                [_callsite_line(cs) for cs in call_sites[:MAX_CALL_SITES]])

    # Section 4: call sites in files that define a referenced type
    type_files = {t["def_file"] for t in type_hits if "def_file" in t}
    related_sites = [cs for cs in all_sites
                     if cs["file"] in type_files and cs["file"] not in changed]
    add_section("related_call_sites", "RELATED CALL SITES (TYPE DEFINITIONS)",
                [_callsite_line(cs) for cs in related_sites[:MAX_RELATED_CALL_SITES]])

    # Section 5: what was left out, by name only, so its absence reads as
    # deliberate rather than as a gap in the index
    add_section("omitted", "OMITTED (indexed entries this diff removes or "
                "rewrites)", omitted)

    # Nothing matched: return no pack at all rather than a bare header
    # with no facts under it. Each entry line's end offset in the text is
    # kept, so the report can count what truncation leaves.
    header = "/*** REPO CONTEXT — INDEXED SNAPSHOT ***/\n"
    texts, line_ends, offset = [header], [], len(header)
    for key, title, entry_lines in sections:
        offset += 1 + len(f"--- {title} ---")  # the join's newline, the title
        for line in entry_lines:
            offset += 1 + len(line)
            line_ends.append((key, offset))
        offset += 1  # the section's closing newline
        texts.append("\n".join([f"--- {title} ---", *entry_lines]) + "\n")
    context_text = "\n".join(texts).strip() if sections else ""
    kept = len(context_text)
    marker = "\n[... context truncated ...]"
    truncated = kept > budget
    if truncated:
        # The marker lives inside the budget.
        kept = max(0, budget - len(marker))
        context_text = context_text[:kept] + marker

    report["used"] = len(context_text)
    # Matches per section; the caps and truncation decide what is shown.
    report["sections"] = {
        "modified_files": len(mod_files),
        "types": len(type_hits),
        "constants": len(const_hits),
        "call_sites": len(call_sites),
        "related_call_sites": len(related_sites),
    }
    report["entries"] = sum(report["sections"].values())
    report["sections"]["omitted"] = len(omitted)  # named, not counted as facts
    # Lines per section in the text the model sees: a meta-file line names
    # several files, and a line cut by truncation is not counted.
    report["shown"] = {key: sum(1 for k, end in line_ends if k == key and end <= kept)
                       for key in report["sections"]}
    report["truncated"] = truncated

    return (context_text, report)
