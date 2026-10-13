"""Offline repo indexer — builds repo_context.json for a target codebase.

Two-tier extraction:
  - Deterministic (free, CI-safe): file walk, typedef harvesting,
    constant extraction, queued-connection call sites, layer
    classification via file_metadata.
  - LLM-assisted (optional, cached): one-line purpose summaries per file.
    Cached by content hash, model and summary-prompt version; only
    changed files re-summarize.

Output is a checked-in artifact — the codebase's context pack that
debate.py retrieves from at review time (build_context_pack below).
Regenerate explicitly:
    python orchestrator.py --index ../qttune [--no-llm]

IMPORTANT: run --index from the LLMOrchestrator directory. Paths in
repo_context.json are relative to the TARGET repo root.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agent_client import call_agent
from config import MODELS, TEMPERATURE_RETRY

CONTEXT_FILE = "repo_context.json"

# Layer keywords used to hint purpose summaries (fast path when --no-llm)
_PURPOSE_HINTS = {
    "test": "Test suite",
    "CMakeLists": "Build configuration",
    ".github": "CI workflow",
    "README": "Project documentation",
    "docs/": "Documentation",
}

# Bump when SUMMARY_PROMPT changes: it keys the summary cache.
SUMMARY_PROMPT_VERSION = "s2-json-purpose"

# MODEL-FACING text (feeds debate.py's prompt_fingerprint — a change here
# is a prompt change; PROMPT_VERSION must be bumped alongside).
PACK_BUDGET = 6000

# call_agent forces Ollama JSON mode, so the prompt must ask for JSON with
# a named key (a bare-sentence request made models invent keys, and the
# path or a failure marker got stored as the purpose).
SUMMARY_PROMPT = """You are documenting a codebase for automated code review.
Given ONE file from the project, describe its purpose in a single sentence
(what it does, who calls it, what it defines). Reference concrete names
(classes, functions, key constants) where useful.

Respond ONLY with this JSON object:
{"purpose": "<one sentence>"}"""

_NUM = r"-?(?:0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)[uUlLfF]*"

DEFINE_RE = re.compile(
    r"^[ \t]*#[ \t]*define[ \t]+([A-Za-z_]\w*)[ \t]+\(?[ \t]*(" + _NUM +
    r")[ \t]*\)?[ \t]*$", re.MULTILINE)

CONST_DECL_RE = re.compile(
    r"^[ \t]*(?:(?:static|inline|extern)[ \t]+)*(?:const|constexpr)[ \t]+"
    r"(?:(?:const|constexpr|static|inline|unsigned|signed|long|short|volatile)[ \t]+)*"
    r"[A-Za-z_][\w:]*[ \t*&]+([A-Za-z_]\w*)[ \t]*(?:=[ \t]*|\{[ \t]*)(" + _NUM +
    r")[ \t]*[;},]", re.MULTILINE)

_AGGREGATE_HEAD = re.compile(r"typedef\s+(struct|union|enum)\b\s*\w*\s*\{")
_FUNC_PTR = re.compile(r"typedef\s+[^;{}]*?\(\s*\*\s*(\w+)\s*\)\s*\(")
_SIMPLE_TYPEDEF = re.compile(r"typedef\s+([^;{}()]*?)\b(\w+)\s*(?:\[[^\]]*\]\s*)*;")
_MEMBER_FUNC_PTR = re.compile(r"\(\s*\*\s*(\w+)\s*\)")
_DECL_NAME = re.compile(r"(\w+)\s*(?:\[[^\]]*\]\s*)*(?::\s*\w+\s*)?$")

QUEUED_CONN_RE = re.compile(r"\bQt::(?:Blocking)?QueuedConnection\b")
_STATEMENT_LEADS = ("connect", "invokeMethod")

def _match_paren_forward(s: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1

def _callee_start(s: str, open_paren: int) -> int:
    """Start offset of the call expression ending at open_paren
    ('QMetaObject::invokeMethod', 'connect', 'obj.connect')."""
    i = open_paren - 1
    while i >= 0 and (s[i].isalnum() or s[i] in "_.:"):
        i -= 1
    return i + 1

def _enclosing_lead_call(blanked: str, pos: int) -> Optional[Tuple[int, int, int]]:
    """The (innermost or enclosing) connect()/invokeMethod() call whose
    argument list contains pos. Returns (stmt_start, open_paren,
    close_paren) or None. Paren-depth scanning treats semicolons inside
    lambda bodies as invisible — unlike statement-bound heuristics."""
    cursor = pos
    while True:
        depth, i, open_paren = 0, cursor - 1, -1
        while i >= 0:
            c = blanked[i]
            if c == ")":
                depth += 1
            elif c == "(":
                if depth == 0:
                    open_paren = i
                    break
                depth -= 1
            i -= 1
        if open_paren == -1:
            return None
        callee = blanked[_callee_start(blanked, open_paren):open_paren]
        matched = any(callee == lead or callee.endswith("::" + lead)
                      or callee.endswith("." + lead)
                      for lead in _STATEMENT_LEADS)
        if matched:
            close = _match_paren_forward(blanked, open_paren)
            if close == -1:
                return None
            stmt_start = blanked.rfind(
                "\n", 0, _callee_start(blanked, open_paren)) + 1
            return stmt_start, open_paren, close
        cursor = open_paren  # keep scanning outward (e.g. SLOT(run()) args)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _header_purpose(text: str) -> Optional[str]:
    for line in text.split("\n"):
        s = line.strip()
        if not (s.startswith("//") and len(s) > 10):
            continue
        body = s.lstrip("/").strip()
        core = body.strip("-= *_")
        if len(core) < 8:
            continue
        letters = sum(1 for c in core if c.isalpha() or c.isspace())
        if letters < len(core) * 0.6:
            continue
        return core[:200]
    return None


# ============ C/C++ SOURCE SCANNING ============

def _blank_comments(text: str) -> str:
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


def _match_brace(s: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top_level(body: str, sep: str) -> List[str]:
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch in "{(":
            depth += 1
        elif ch in "})":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur)
    if tail.strip():
        parts.append(tail)
    return parts


def _member_names(body: str) -> List[str]:
    names = []
    for decl in _split_top_level(body, ";"):
        for i, part in enumerate(_split_top_level(decl, ",")):
            part = part.strip()
            if not part:
                continue
            fp = _MEMBER_FUNC_PTR.search(part)
            if fp:
                names.append(fp.group(1))
                continue
            if i == 0 and "{" in part:
                part = part[part.rfind("}") + 1:]
            m = _DECL_NAME.search(part.strip())
            if m:
                names.append(m.group(1))
    return names


def _enum_values(body: str) -> Dict[str, Optional[str]]:
    values = {}
    for part in _split_top_level(body, ","):
        name, _, value = part.partition("=")
        name = name.strip()
        if re.fullmatch(r"[A-Za-z_]\w*", name):
            values[name] = " ".join(value.split()) or None
    return values


def _doc_comment(text: str, start: int) -> Optional[str]:
    before = text[:start].rstrip()
    if before.endswith("*/"):
        j = before.rfind("/*")
        line_start = before.rfind("\n", 0, j) + 1
        if j != -1 and not before[line_start:j].strip():
            lines = [ln.strip().lstrip("*").strip()
                     for ln in before[j + 2:-2].split("\n")]
            return " ".join(ln for ln in lines if ln) or None
        return None
    lines = []
    for line in reversed(before.split("\n")):
        s = line.strip()
        if not s.startswith("//"):
            break
        lines.append(s.lstrip("/").strip())
    return " ".join(reversed(lines)) or None


def harvest_typedefs(text: str) -> List[Dict]:
    blanked = _blank_comments(text)
    out = []
    for m in re.finditer(r"\btypedef\b", blanked):
        pos = m.start()
        entry = None
        head = _AGGREGATE_HEAD.match(blanked, pos)
        if head:
            open_idx = head.end() - 1
            close = _match_brace(blanked, open_idx)
            if close == -1:
                continue
            tail = re.match(r"\s*\**\s*(\w+)[^;]*;", blanked[close + 1:])
            if not tail:
                continue
            end = close + 1 + tail.end()
            body = blanked[open_idx + 1:close]
            kind = head.group(1)
            entry = {"name": tail.group(1), "kind": kind}
            if kind == "enum":
                values = _enum_values(body)
                entry["members"] = list(values)
                entry["values"] = values
            else:
                entry["members"] = _member_names(body)
        else:
            semi = blanked.find(";", pos)
            if semi == -1:
                continue
            segment = blanked[pos:semi + 1]
            end = semi + 1
            fp = _FUNC_PTR.match(segment)
            simple = None if fp else _SIMPLE_TYPEDEF.match(segment)
            if fp:
                entry = {"name": fp.group(1), "kind": "function_pointer",
                         "members": []}
            elif simple:
                base = simple.group(1).split()
                opaque = bool(base) and base[0] in ("struct", "union")
                entry = {"name": simple.group(2),
                         "kind": "opaque" if opaque else "alias",
                         "members": []}
            else:
                continue
        entry["decl"] = text[pos:end].strip()[:2000]
        entry["doc"] = _doc_comment(text, pos)
        out.append(entry)
    return out


def harvest_constants(text: str, file_path: str) -> List[Dict]:
    blanked = _blank_comments(text)
    found = []
    for kind, regex in (("define", DEFINE_RE), ("const", CONST_DECL_RE)):
        for m in regex.finditer(blanked):
            found.append((m.start(), kind, m.group(1), m.group(2)))
    out = []
    for _, kind, name, value in sorted(found):
        if name.startswith(("q_", "_")):
            continue
        out.append({"name": name, "value": value, "kind": kind,
                    "file": file_path})
    return out

def harvest_callsites(text: str, file_path: str) -> List[Dict]:
    """Cross-thread handoff points: connect()/invokeMethod() statements
    using a queued connection. Snippet spans the WHOLE call statement,
    found by paren matching — lambda bodies of any length included.
    Commented-out calls are ignored (comments blanked before scanning).
    
    If the statement exceeds 400 chars, the snippet shows:
      begin (connect signature) + " ..." + end (Qt::QueuedConnection part)"""
    blanked = _blank_comments(text)
    out = []
    for m in QUEUED_CONN_RE.finditer(blanked):
        bounds = _enclosing_lead_call(blanked, m.start())
        if bounds is None:
            # not inside a recognized call: fall back to line bounds
            start = blanked.rfind("\n", 0, m.start()) + 1
            nl = blanked.find("\n", m.start())
            end = nl if nl != -1 else len(blanked)
        else:
            start, _, close = bounds
            end = close + 1
            j = end
            while j < len(blanked) and blanked[j] in " \t":
                j += 1
            if j < len(blanked) and blanked[j] == ";":
                end = j + 1
        
        full_snippet = " ".join(text[start:end].split())
        
        if len(full_snippet) > 400:
            begin = full_snippet[:150]
            tail = full_snippet[-250:]
            if "QueuedConnection" in tail:
                # Tail already carries the connection type: head + ellipsis + tail
                snippet = begin + " ... " + tail
            else:
                # Connection type is buried mid-body: splice it in explicitly
                queueloc = full_snippet.find("QueuedConnection")
                if queueloc != -1:
                    snippet = (begin + " ... "
                               + full_snippet[max(0, queueloc - 20):queueloc + 30])
                else:
                    snippet = full_snippet[:400]
        else:
            snippet = full_snippet
        
        out.append({
            "file": file_path,
            "line": blanked.count("\n", 0, start) + 1,
            "snippet": snippet,
            "doc": _doc_comment(text, start),
        })
    return out


# ============ LLM PURPOSE SUMMARIES ============

def _validate_purpose(raw) -> Tuple[Optional[dict], Optional[str]]:
    if isinstance(raw, dict) and isinstance(raw.get("purpose"), str) \
            and len(raw["purpose"].strip()) > 10:
        return {"purpose": raw["purpose"].strip()}, None
    return None, 'expected {"purpose": "<one sentence>"}'


def llm_purpose(model: str, file_path: str, text: str) -> Optional[str]:
    snippet = "\n".join(text.split("\n")[:120])
    result = call_agent(model, SUMMARY_PROMPT,
                        f"FILE: {file_path}\n\n{snippet}", TEMPERATURE_RETRY,
                        validate=_validate_purpose)
    if result.get("verdict") == "PARSE_FAILURE":
        return None
    return result["purpose"][:200]


# ============ INDEX BUILD ============

_SKIP_DIRS = {".git", "build", ".venv", "__pycache__", "node_modules"}
_SKIP_DIR_PREFIXES = ("build-", "cmake-build-")


def _skipped(rel_parts) -> bool:
    return any(p in _SKIP_DIRS or p.startswith(_SKIP_DIR_PREFIXES)
               for p in rel_parts[:-1])


def build_index(target_root: str, use_llm: bool = True) -> dict:
    root = Path(target_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"ERROR: target repo not found: {root}")

    summary_model = MODELS["auto_engineer"]
    index = {
        "index_version": None,
        "llm_summaries": use_llm,
        "summary_model": summary_model if use_llm else None,
        "summary_prompt_version": SUMMARY_PROMPT_VERSION if use_llm else None,
        "files": [],
        "types": [],
        "constants": [],
        "callsites": [],  # NEW: queued-connection call sites
    }

    src_exts = {".c", ".cpp", ".h", ".hpp", ".qml"}
    seen_types, seen_consts = {}, {}
    cache = _load_cache() if use_llm else {}

    for path in sorted(root.rglob("*")):
        rel_path = path.relative_to(root)
        if not path.is_file() or _skipped(rel_path.parts):
            continue
        rel = rel_path.as_posix()
        if path.suffix not in src_exts:
            if path.suffix in (".md", ".yml", ".yaml") or "CMakeLists" in path.name:
                index["files"].append({
                    "path": rel, "purpose": _PURPOSE_HINTS.get(
                        next((k for k in _PURPOSE_HINTS if k in rel), ""),
                        "Configuration or docs"),
                    "layer": "meta",
                })
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        digest = _sha256(path)

        purpose = None
        if not use_llm:
            purpose = _header_purpose(text)
        else:
            entry = cache.get(rel) or {}
            if (entry.get("digest") == digest
                    and entry.get("model") == summary_model
                    and entry.get("prompt_version") == SUMMARY_PROMPT_VERSION):
                purpose = entry.get("purpose")
            if not purpose:
                purpose = llm_purpose(summary_model, rel, text)
                cache[rel] = {"digest": digest, "model": summary_model,
                              "prompt_version": SUMMARY_PROMPT_VERSION,
                              "purpose": purpose or ""}
                _save_cache(cache)

        index["files"].append({
            "path": rel,
            "purpose": (purpose or "").strip()[:200],
            "layer": None,
        })

        for t in harvest_typedefs(text):
            if t["name"] not in seen_types:
                t["def_file"] = rel
                seen_types[t["name"]] = t
        for c in harvest_constants(text, rel):
            key = (c["name"], c["file"])
            if key not in seen_consts:
                seen_consts[key] = c
        # HARVESTER ADDED HERE
        for cs in harvest_callsites(text, rel):
            index["callsites"].append(cs)

    index["types"] = list(seen_types.values())
    index["constants"] = list(seen_consts.values())

    from file_metadata import identify_layer
    for f in index["files"]:
        if f.get("layer") is None:
            f["layer"] = identify_layer(f["path"])

    return index


def _cache_path() -> Path:
    return Path("repo_context_cache.json")


def _load_cache() -> dict:
    p = _cache_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    _cache_path().write_text(json.dumps(cache, indent=2), encoding="utf-8")


def save_index(index: dict) -> Path:
    index["index_version"] = (
        f"idx_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    out = Path(CONTEXT_FILE)
    out.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return out


# ============ RETRIEVAL FUNCTION (NEW SECTION) ============

def _diff_paths(code_diff: str) -> List[str]:
    """Extract all +++ b/ paths from a diff."""
    paths = []
    for line in code_diff.split("\n"):
        if line.startswith("+++ b/"):
            paths.append(line.replace("+++ b/", "").strip())
    return paths


def _referenced_identifiers(code_diff: str) -> List[str]:
    """Pull identifiers that look like qttune_* or CamelCase type names."""
    ids = set()
    for m in re.finditer(r"\b(qttune_[A-Za-z_]\w*)\b", code_diff):
        ids.add(m.group(1))
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9_]*)(?:<[^\s>]+>)?", code_diff):
        if m.group(1).isupper():
            continue
        ids.add(m.group(1))
    return list(ids)


def build_context_pack(code_diff: str, index: dict,
                       budget: int = PACK_BUDGET) -> Tuple[str, dict]:
    """Retrieve ground-truth context for a given diff. Returns (context_text,
    pack_report). The pack_report contains budget accounting for ADR provenance.
    
    Priority order within budget:
    1. Files directly modified (from +++ b/ headers)
    2. Types/constants referenced by identifier in the diff
    3. Queued-connection call sites in the affected files
    4. Adjacent directory neighbors (if budget remains)
    """
    report = {
        "budget": budget,
        "used": 0,
        "sections": {},
        "entries": 0,
        "error": None,
    }

    if not index.get("files"):
        report["error"] = "empty or missing index"
        return ("", report)

    diff_paths = _diff_paths(code_diff)
    ref_ids = _referenced_identifiers(code_diff)

    lines = ["""/*** REPO CONTEXT — GROUND TRUTH ***/\n"""]
    chars_used = 0

    # Section 1: Modified files (purpose + layer)
    mod_files = [f for f in index["files"] if f["path"] in diff_paths]
    if mod_files:
        section_lines = ["--- MODIFIED FILES ---"]
        for f in mod_files[:20]:  # cap per-file
            purpose = f.get("purpose") or "(no purpose available)"
            layer = f.get("layer") or "unknown"
            section_lines.append(f"[{f['path']}] ({layer}): {purpose}")
        section_text = "\n".join(section_lines) + "\n"
        chars_used += len(section_text)
        lines.append(section_text)

    # Section 2: Referenced types/constants
    type_hits = [t for t in index["types"] if t["name"] in ref_ids]
    const_hits = [c for c in index["constants"] if c["name"] in ref_ids]
    if type_hits or const_hits:
        section_lines = ["--- KNOWN TYPES ---"]
        for t in type_hits[:10]:  # cap types
            doc = t.get("doc") or ""
            members = ", ".join(t.get("members", [])[:5])
            section_lines.append(f"{t['name']} ({t['kind']}): {members}"[:100])
        section_lines.append("\n--- CONSTANTS ---")
        for c in const_hits[:10]:  # cap constants
            section_lines.append(f"{c['name']} = {c['value']} ({c['kind']})")
        section_text = "\n".join(section_lines) + "\n"
        chars_used += len(section_text)
        lines.append(section_text)

    # Section 3: Queued-connection call sites (THE KEY FIX FOR THREAD SAFETY)
    affected_files_set = set(diff_paths)
    call_sites = [cs for cs in index.get("callsites", [])
                  if cs["file"] in affected_files_set]
    if call_sites:
        section_lines = ["--- QUEUED CONNECTION CALL SITES ---"]
        for cs in call_sites[:15]:
            snippet = (cs.get("snippet") or "")[:120]
            doc = cs.get("doc") or ""
            section_lines.append(
                f"[{cs['file']}:{cs['line']}] {snippet}"
                + (f" // {doc}" if doc else "")
            )
        section_text = "\n".join(section_lines) + "\n"
        chars_used += len(section_text)
        lines.append(section_text)
        # Also add call sites for files mentioned by types
        type_file_set = {t["def_file"] for t in type_hits if "def_file" in t}
        extra_sites = [cs for cs in index.get("callsites", [])
                       if cs["file"] in type_file_set
                       and cs["file"] not in affected_files_set]
        if extra_sites:
            section_lines = ["--- RELATED CALL SITES (TYPE DEFINITIONS) ---"]
            for cs in extra_sites[:10]:
                snippet = (cs.get("snippet") or "")[:120]
                section_lines.append(f"[{cs['file']}:{cs['line']}] {snippet}")
            section_text = "\n".join(section_lines) + "\n"
            chars_used += len(section_text)
            lines.append(section_text)

    marker = "\n[... context truncated ...]"
    context_text = "\n".join(lines)
    if chars_used > budget:
        # Marker lives INSIDE the budget: report['used'] must match
        # what the model actually sees, per-ADR accounting.
        context_text = context_text[:max(0, budget - len(marker))] + marker
        chars_used = budget

    report["used"] = chars_used
    report["sections"] = {
        "modified_files": len(mod_files),
        "types": len(type_hits),
        "constants": len(const_hits),
        "call_sites": len(call_sites),
    }
    report["entries"] = (
        len(mod_files) + len(type_hits) + len(const_hits) + len(call_sites)
    )

    return (context_text.strip(), report)


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "../qttune"
    idx = build_index(target, use_llm="--no-llm" not in sys.argv)
    p = save_index(idx)
    print(f"Wrote {p}: {len(idx['files'])} files, "
          f"{len(idx['types'])} types, {len(idx['constants'])} constants, "
          f"{len(idx['callsites'])} call sites")
    