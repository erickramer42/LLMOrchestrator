"""Offline repo indexer — builds repo_context.json for a target codebase.

Two-tier extraction:
  - Deterministic (free, CI-safe): file walk, typedef harvesting,
    constant extraction, layer classification via file_metadata.
  - LLM-assisted (optional, cached): one-line purpose summaries per file.
    Cached by content hash; only changed files re-summarize.

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
from typing import Dict, List, Optional

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

TYPEDEF_RE = re.compile(
    r"(?:^|\n)\s*(typedef\s+(?:struct|enum)\s*\w*\s*\{[^}]*\}\s*\w+\s*;)",
    re.MULTILINE)

CONSTANT_RE = re.compile(
    r"(?:^|\n)\s*(?:static\s+)?(?:const\s+)?(?:constexpr\s+)?"
    r"[A-Za-z_][A-Za-z0-9_]*\s+(\w+)\s*=\s*(-?\d+(?:\.\d+)?f?)\s*[;/{(]",
    re.MULTILINE)

SUMMARY_PROMPT = """You are documenting a codebase for automated code review.
Given ONE file from the project, write a single sentence describing its
purpose (what it does, who calls it, what it defines). Reference concrete
names (classes, functions, key constants) where useful. No preamble, no
markdown, just the sentence."""


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


def harvest_typedefs(text: str) -> List[Dict]:
    """Extract C struct/enum typedefs with struct member summary."""
    out = []
    for m in TYPEDEF_RE.finditer(text):
        body = m.group(1)
        name_m = re.search(r"\}\s*(\w+)\s*;", body)
        if not name_m:
            continue
        name = name_m.group(1)
        members = re.findall(r"(\w+)\s*;", body)
        # Skip braces content for member names; capture declarations instead
        decls = re.findall(r"[;\{]\s*(?:unsigned\s+|signed\s+)?"
                            r"(?:const\s+)?\w+[\s\*]+(\w+)\s*(?:\[[^\]]*\])?\s*;",
                            body)
        out.append({
            "name": name,
            "decl": body.strip()[:2000],   # full definition, capped
            "members": decls[:20],
        })
    return out


def harvest_constants(text: str, file_path: str) -> List[Dict]:
    """Extract numeric constants (targets, thresholds, limits)."""
    out = []
    for m in CONSTANT_RE.finditer(text):
        name, value = m.group(1), m.group(2)
        if name.startswith(("q_", "_")):
            continue
        out.append({"name": name, "value": value, "file": file_path})
    return out


def llm_purpose(model: str, file_path: str, text: str) -> Optional[str]:
    """One-line purpose via LLM. Returns None on failure (caller falls
    back to the path-derived hint)."""
    snippet = "\n".join(text.split("\n")[:120])  # cap input
    try:
        result = call_agent(
            model, SUMMARY_PROMPT,
            f"FILE: {file_path}\n\n{snippet}", TEMPERATURE_RETRY)
        # JSON-mode returns a dict; take any string-ish value we can find
        for v in result.values():
            if isinstance(v, str) and len(v) > 10:
                return v.strip()[:200]
    except Exception:
        pass
    return None


def build_index(target_root: str, use_llm: bool = True) -> dict:
    """Walk the target repo and produce the context-pack structure."""
    root = Path(target_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"ERROR: target repo not found: {root}")

    index = {
        "index_version": None,  # set on save
        "repo_root": str(root),
        "files": [],
        "types": [],
        "constants": [],
    }

    src_exts = {".c", ".cpp", ".h", ".hpp", ".qml"}
    seen_types, seen_consts = {}, {}

    skip_dirs = {".git", "build", ".venv", "__pycache__", "node_modules"}

    for path in sorted(root.rglob("*")):
        if any(part in skip_dirs for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
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
            cached = _load_cache()
            entry = cached.get(rel)
            if entry and entry.get("digest") == digest:
                purpose = entry.get("purpose")
            if not purpose:
                purpose = llm_purpose(MODELS["auto_engineer"], rel, text)
                cached[rel] = {"digest": digest, "purpose": purpose or ""}
                _save_cache(cached)

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
    