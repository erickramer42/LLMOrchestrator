"""Offline repo indexer — builds repo_context.json for a target codebase.

Two-tier extraction:
  - Deterministic (free, CI-safe): file walk, typedef harvesting,
    constant extraction, layer classification via file_metadata.
  - LLM-assisted (optional, cached): one-line purpose summaries per file.
    Cached by content hash, model and summary-prompt version; only
    changed files re-summarize.

Output is a checked-in artifact — the codebase's context pack that
debate.py retrieves from at review time. Regenerate explicitly:
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

# Only declarations marked const/constexpr: plain 'int count = 0;' is a
# variable, not a limit or threshold.
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _header_purpose(text: str) -> Optional[str]:
    """First plausible purpose line among '//' comments. Skips banner
    dividers ('---- Section ----') and fragments that are mostly
    punctuation. Returns None when nothing credible is found."""
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
    """Same-length copy of C/C++ source with comments replaced by spaces
    (newlines kept), so offsets map back to the original text. String and
    char literals are skipped so '//' inside them survives."""
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
    """Split on sep, ignoring separators nested in braces/parentheses."""
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
    """Declared member names of a struct/union body (comments blanked).
    Handles arrays, bit-fields, pointers, function-pointer members,
    'int a, b;' lists and nested struct/union members."""
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
                part = part[part.rfind("}") + 1:]  # nested aggregate: name after '}'
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
    """The comment block directly above offset start (only whitespace in
    between), e.g. '/* Callback ... called from transport thread */'."""
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
    """Extract C typedefs: struct/union/enum definitions (with member
    names and enum values), opaque handles ('typedef struct x x_t;'),
    function-pointer callbacks and plain aliases. Each entry keeps the
    original declaration text and the comment directly above it."""
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
        entry["decl"] = text[pos:end].strip()[:2000]   # original, with comments
        entry["doc"] = _doc_comment(text, pos)
        out.append(entry)
    return out


def harvest_constants(text: str, file_path: str) -> List[Dict]:
    """Extract numeric constants (targets, thresholds, limits): #define
    values and const/constexpr declarations. Comments are ignored, so
    commented-out code is not harvested."""
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


# ============ LLM PURPOSE SUMMARIES ============

def _validate_purpose(raw) -> Tuple[Optional[dict], Optional[str]]:
    if isinstance(raw, dict) and isinstance(raw.get("purpose"), str) \
            and len(raw["purpose"].strip()) > 10:
        return {"purpose": raw["purpose"].strip()}, None
    return None, 'expected {"purpose": "<one sentence>"}'


def llm_purpose(model: str, file_path: str, text: str) -> Optional[str]:
    """One-line purpose via LLM. Returns None on failure (the caller stores
    an empty purpose, which is retried on the next run)."""
    snippet = "\n".join(text.split("\n")[:120])  # cap input
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
    """Skip build/VCS directories, judged on the path RELATIVE to the
    target root so a checkout living under e.g. C:/build/ still indexes."""
    return any(p in _SKIP_DIRS or p.startswith(_SKIP_DIR_PREFIXES)
               for p in rel_parts[:-1])


def build_index(target_root: str, use_llm: bool = True) -> dict:
    """Walk the target repo and produce the context-pack structure."""
    root = Path(target_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"ERROR: target repo not found: {root}")

    summary_model = MODELS["auto_engineer"]
    index = {
        "index_version": None,  # set on save
        "repo_root": str(root),
        "llm_summaries": use_llm,
        "summary_model": summary_model if use_llm else None,
        "summary_prompt_version": SUMMARY_PROMPT_VERSION if use_llm else None,
        "files": [],
        "types": [],
        "constants": [],
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
            # still index interesting non-source files for the map
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

        # deterministic purpose: first credible header comment, else LLM
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
            "layer": None,  # filled below via identify_layer
        })

        for t in harvest_typedefs(text):
            if t["name"] not in seen_types:
                t["def_file"] = rel
                seen_types[t["name"]] = t
        for c in harvest_constants(text, rel):
            key = (c["name"], c["file"])
            if key not in seen_consts:
                seen_consts[key] = c

    index["types"] = list(seen_types.values())
    index["constants"] = list(seen_consts.values())

    # classify layers post-hoc (file_metadata is substring-based);
    # files already tagged "meta" (docs/CI/build) keep that tag
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


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "../qttune"
    idx = build_index(target, use_llm="--no-llm" not in sys.argv)
    p = save_index(idx)
    print(f"Wrote {p}: {len(idx['files'])} files, "
          f"{len(idx['types'])} types, {len(idx['constants'])} constants")
