"""Offline repo indexer — builds repo_context.json for a target codebase.

Two-tier extraction:
  - Deterministic (free, CI-safe): file walk, typedef harvesting,
    constant extraction, queued-connection call sites, layer
    classification via file_metadata.
  - LLM-assisted (optional, cached): one-line purpose summaries per file.
    Cached by content hash, model and summary-prompt version; only
    changed files re-summarize.

Output is a checked-in artifact — the codebase's context pack that
retrieval.py retrieves from at review time. Regenerate explicitly:
    python orchestrator.py --index ../qttune [--no-llm]

The index and the summary cache are written next to this module, from
any working directory; the target path is relative to the working
directory. Paths in repo_context.json are relative to the TARGET repo
root.

Purposes and call-site snippets are rendered here and shown as stored,
so changing how they render changes the pack: bump
retrieval.PACK_FORMAT_VERSION.
"""

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agent_client import call_agent
from config import MODELS, TEMPERATURE_RETRY
from file_metadata import identify_layer
from retrieval import (CONTEXT_PATH, PURPOSE_LIMIT, QUEUED_CONN_RE,
                       SNIPPET_LIMIT, blank_comments, clip)

CACHE_PATH = Path(__file__).resolve().parent / "repo_context_cache.json"

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

_STATEMENT_LEADS = ("connect", "invokeMethod")

# A called name with at most one receiver: 'm_flag.store(', 'self->run('.
_CALLED = re.compile(r"\b((?:[A-Za-z_]\w*(?:->|\.))?[A-Za-z_]\w*)\s*\(")
_NOT_CALLS = {"if", "for", "while", "switch", "return", "sizeof", "catch",
              "static_cast", "reinterpret_cast", "const_cast", "dynamic_cast",
              "decltype", "alignof", "noexcept", "new", "delete"}


def _match_paren_forward(s: str, open_idx: int) -> int:
    """Index of the ')' closing the '(' at open_idx, or -1. Run on
    comment-blanked text, so parentheses in comments do not count."""
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


def _file_digest(path: Path) -> str:
    """The first 12 hex chars of the file's SHA-256: the summary cache's
    key for its content."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _header_purpose(text: str) -> Optional[str]:
    """The --no-llm purpose: the first '//' comment line that reads as
    prose (8+ chars, mostly letters), so banners and separators are
    skipped. None when there is none."""
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



def _match_brace(s: str, open_idx: int) -> int:
    """Index of the '}' closing the '{' at open_idx, or -1."""
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top_level(body: str, sep: str, openers: str = "{(",
                     closers: str = "})") -> List[str]:
    """Split on sep, ignoring separators nested inside openers/closers.
    Call arguments need '[' too, for lambda capture lists."""
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch in openers:
            depth += 1
        elif ch in closers:
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
    """Member names of a struct or union body, in order: 'int a, b;'
    gives a and b, a function-pointer member its name, and a nested
    aggregate the name after its closing brace."""
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
    """Enumerator name -> its initializer text, or None when implicit."""
    values = {}
    for part in _split_top_level(body, ","):
        name, _, value = part.partition("=")
        name = name.strip()
        if re.fullmatch(r"[A-Za-z_]\w*", name):
            values[name] = " ".join(value.split()) or None
    return values


def _doc_comment(text: str, start: int) -> Optional[str]:
    """The comment directly above offset start, as one line: a /* */
    block that ends just before it and starts its own line, or the run of
    '//' lines just before it. None when there is none."""
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
    """Every C typedef in a source file. Each entry: name, kind (struct,
    union, enum, opaque, function_pointer or alias), members (and values
    for an enum), decl (the original declaration, at most 2000 chars) and
    doc (the comment above it). Commented-out typedefs are ignored."""
    blanked = blank_comments(text)
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
    """Numeric constants of a source file, in source order: '#define N 64'
    and const/constexpr declarations with a numeric initializer. Each
    entry: name, value (as written), kind ('define' or 'const') and file.
    Names starting with 'q_' or '_' are skipped."""
    blanked = blank_comments(text)
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

def _lambda_summary(arg: str) -> str:
    """Compact form of a lambda argument: its capture list and parameters,
    plus the functions its body calls, e.g.
    '[self, copy]() { calls: fetch_sub, handleFrameInternal }'.
    The body itself is dropped: it is long and mostly irrelevant to WHERE
    work is handed off to."""
    brace = arg.find("{")
    head = " ".join(arg[:brace].split())
    close = _match_brace(arg, brace)
    body = arg[brace + 1:close if close != -1 else len(arg)]
    calls: List[str] = []
    for m in _CALLED.finditer(body):
        name = m.group(1)
        if re.split(r"->|\.", name)[-1] in _NOT_CALLS:
            continue
        for owner in ("self->", "this->"):  # the context object is implied
            if name.startswith(owner):
                name = name[len(owner):]
        if name not in calls:
            calls.append(name)
    inner = f"calls: {', '.join(calls[:6])}" if calls else "..."
    return f"{head} {{ {inner} }}"


def _render_call(callee: str, args_text: str, connection: str,
                 semicolon: bool) -> str:
    """One-line rendering of a queued call from comment-blanked source.
    Lambda arguments are summarized; the connection type is always kept
    visible, even when the line has to be shortened."""
    parts = []
    for arg in _split_top_level(args_text, ",", "{([", "})]"):
        arg = arg.strip()
        parts.append(_lambda_summary(arg) if arg.startswith("[") and "{" in arg
                     else " ".join(arg.split()))
    end = ");" if semicolon else ")"
    rendered = f"{callee}({', '.join(parts)}{end}"
    if len(rendered) <= SNIPPET_LIMIT:
        return rendered
    keep = SNIPPET_LIMIT - len(connection) - len(end) - 3
    return f"{rendered[:keep].rstrip(' ,')} … {connection}{end}"


def harvest_callsites(text: str, file_path: str) -> List[Dict]:
    """Cross-thread handoff points: connect()/invokeMethod() statements
    using a queued connection. The whole call is located by paren
    matching (lambda bodies of any length included) and rendered from
    COMMENT-BLANKED text, so comments inside lambda bodies never crowd
    out the call itself. Commented-out calls are ignored.

    Each entry: file, line, snippet (rendered call, <= SNIPPET_LIMIT,
    connection type always visible), connection, doc (comment above)."""
    blanked = blank_comments(text)
    out = []
    for m in QUEUED_CONN_RE.finditer(blanked):
        connection = m.group(0)
        bounds = _enclosing_lead_call(blanked, m.start())
        if bounds is None:
            # not inside a recognized call: fall back to the line itself
            start = blanked.rfind("\n", 0, m.start()) + 1
            nl = blanked.find("\n", m.start())
            line_text = " ".join(blanked[start:nl if nl != -1 else len(blanked)].split())
            snippet = line_text
            if len(snippet) > SNIPPET_LIMIT:
                at = snippet.find(connection)
                lo = max(0, at + len(connection) - SNIPPET_LIMIT + 2)
                snippet = "…" + snippet[lo:lo + SNIPPET_LIMIT - 2] + "…"
        else:
            start, open_paren, close = bounds
            callee = blanked[_callee_start(blanked, open_paren):open_paren]
            j = close + 1
            while j < len(blanked) and blanked[j] in " \t\r":
                j += 1
            semicolon = j < len(blanked) and blanked[j] == ";"
            snippet = _render_call(callee, blanked[open_paren + 1:close],
                                   connection, semicolon)

        out.append({
            "file": file_path,
            "line": blanked.count("\n", 0, start) + 1,
            "snippet": snippet,
            "connection": connection,
            "doc": _doc_comment(text, start),
        })
    return out


# ============ FIELDS AND THEIR WRITERS ============

_AGGREGATE_DEF = re.compile(
    r"^(?:template\s*<[^{};]*>\s*)?(?:typedef\s+)?(class|struct|union)\b\s*"
    r"(?:alignas\s*\([^)]*\)\s*)?(\w+)?\s*(?:final\b\s*)?(?::[^{;]*)?$")
_TRANSPARENT_DEF = re.compile(r'^(?:namespace\b[\w\s:]*|extern\s+"C(?:\+\+)?")$')
_ACCESS_LABEL = re.compile(r"\b(?:(?:public|private|protected)(?:\s+(?:slots|Q_SLOTS))?"
                           r"|signals|Q_SIGNALS)\s*:(?!:)")
_MACRO_LINE = re.compile(r"^\s*[A-Z][A-Z0-9_]*\s*(?:\(.*\))?\s*$")
_NOT_MEMBERS = ("using ", "typedef ", "friend ", "static_assert", "template",
                "enum ", "class ", "struct ", "union ", "return ", "goto ")
_NOT_FUNCTIONS = _NOT_CALLS | {"else", "do", "try", "operator"}
_DECL_KEYWORDS = {"const", "static", "mutable", "volatile", "override", "final",
                  "noexcept", "default", "delete", "constexpr", "inline"}
_FUNC_NAME = re.compile(r"([A-Za-z_~][\w:~]*)\s*$")
_ASSIGN_OP = re.compile(r"(?<![=!<>])(?:<<|>>|[-+*/%&|^])?=(?!=)")
_INC_DEC = re.compile(r"\+\+|--")
_LVALUE_END = re.compile(
    r"([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*|\s*\[[^\[\]]*\])*)\s*$")
_LVALUE_START = re.compile(
    r"^\s*([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*|\s*\[[^\[\]]*\])*)")
_ATOMIC_WRITE = re.compile(
    r"(->|\.)?\s*\b([A-Za-z_]\w*)\s*\.\s*(?:store|exchange|fetch_add|fetch_sub|"
    r"fetch_or|fetch_and|fetch_xor|compare_exchange_weak|compare_exchange_strong)\s*\(")
_CHAIN = re.compile(r"(->|\.)\s*([A-Za-z_]\w*)")


def _clean_head(head: str) -> str:
    """A statement head without preprocessor lines, macro-only lines
    (Q_OBJECT, Q_PROPERTY(...)) and access labels, on one line."""
    lines = [ln for ln in head.split("\n")
             if not ln.lstrip().startswith("#") and not _MACRO_LINE.match(ln)]
    return " ".join(_ACCESS_LABEL.sub(" ", "\n".join(lines)).split())


def _member_decls(statement: str) -> List[str]:
    """The data member names a class-body statement declares: none for a
    method declaration, a type, a using or friend line."""
    if not statement or statement.startswith(_NOT_MEMBERS):
        return []
    names = []
    for part in _split_top_level(statement, ",", "{(<[", "})>]"):
        cut = min((i for i in (part.find("="), part.find("{")) if i != -1),
                  default=len(part))
        declarator = part[:cut]
        if "(" in declarator:  # a method declaration
            return []
        m = _DECL_NAME.search(declarator.strip())
        if m and m.group(1) not in _DECL_KEYWORDS:
            names.append(m.group(1))
    return names


def _function_lines(text: str, start: int, end: int) -> List[str]:
    """A function's comment-free source from start to end, without blank
    lines or trailing space, dedented, with each indent halved and runs
    of inner spaces collapsed."""
    lines = [ln.rstrip() for ln in blank_comments(text)[start:end].split("\n")]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return []
    base = min(len(ln) - len(ln.lstrip()) for ln in lines)
    out = []
    for ln in lines:
        body = ln[base:]
        indent = len(body) - len(body.lstrip())
        out.append(" " * (indent // 2) + " ".join(body.split()))
    return out


def _writes(body: str) -> List[Tuple[str, str]]:
    """(name, form) for each member a function body assigns: through a
    pointer or object ('pointer', 'object': every member of the assigned
    chain, so 't->chans[0].rx_id = x' writes chans and rx_id), an atomic
    operation ('atomic'), or a bare name ('bare', kept only if it is a
    member of the method's class; see build_index). Prefix and postfix
    ++/--, = and compound assignment count; comparisons do not."""
    found = []

    def chain(expr: str) -> None:
        root = re.match(r"\s*([A-Za-z_]\w*)", expr)
        if not root:
            return
        links = _CHAIN.findall(expr[root.end():])
        if root.group(1) == "this" and links:
            found.append((links[0][1], "pointer"))
            links = links[1:]
        else:  # a local, a parameter or a member of the method's class
            found.append((root.group(1), "bare"))
        for op, name in links:
            found.append((name, "pointer" if op == "->" else "object"))

    for m in _ASSIGN_OP.finditer(body):
        lv = _LVALUE_END.search(body[:m.start()])
        if lv:
            chain(lv.group(1))
    for m in _INC_DEC.finditer(body):
        before = _LVALUE_END.search(body[:m.start()])  # postfix: x++
        if before:
            chain(before.group(1))
        after = _LVALUE_START.match(body[m.end():])  # prefix: ++x
        if after:
            chain(after.group(1))
    for m in _ATOMIC_WRITE.finditer(body):
        found.append((m.group(2), "atomic"))
    return found


def harvest_definitions(text: str) -> Tuple[List[Dict], List[Dict]]:
    """The data members of every struct, class and union in a C or C++
    source file, and every function definition with the members it
    assigns. Commented-out code is ignored.

    A member entry: owner (the aggregate's name), name, decl (its
    declaration, comment-free, on one line) and line. A function entry:
    name, owner (the class of a method, from 'A::f' or the class body it
    is defined in; None for a free function), line and end_line, writes
    ({name: [forms]}, bare names unfiltered) and lines (the comment-free
    source, see _function_lines)."""
    blanked = blank_comments(text)
    members: List[Dict] = []
    functions: List[Dict] = []
    line_of = lambda i: blanked.count("\n", 0, i) + 1

    def scan(start: int, end: int, owner: Optional[str]) -> None:
        stmt = start
        i = start
        while i < end:
            c = blanked[i]
            if c == ";":
                if owner is not None:
                    raw = blanked[stmt:i]
                    statement = _clean_head(raw)
                    names = _member_decls(statement)
                    if names:
                        offset = stmt + len(raw) - len(raw.lstrip())
                        for name in names:
                            members.append({"owner": owner, "name": name,
                                            "decl": statement + ";",
                                            "line": line_of(offset)})
                stmt = i + 1
            elif c == "}":
                stmt = i + 1
            elif c == "{":
                close = _match_brace(blanked, i)
                if close == -1 or close > end:
                    return
                raw = blanked[stmt:i]
                head = _clean_head(raw)
                aggregate = _AGGREGATE_DEF.match(head)
                if aggregate:
                    name = aggregate.group(2)
                    if name is None:  # typedef struct { ... } name;
                        tail = re.match(r"\s*\**\s*(\w+)", blanked[close + 1:end])
                        name = tail.group(1) if tail else None
                    if name:
                        scan(i + 1, close, name)
                    stmt = close + 1  # 'struct S { ... } s;' declares s
                    i = close + 1
                    continue
                if _TRANSPARENT_DEF.match(head):
                    scan(i + 1, close, owner)
                    stmt = close + 1
                    i = close + 1
                    continue
                paren = head.find("(")
                pre = head[:paren] if paren != -1 else ""
                # 'f(int a = {})': a default argument, not a body
                balanced = head.count("(") == head.count(")")
                fname = (_FUNC_NAME.search(pre)
                         if paren != -1 and "=" not in pre and balanced else None)
                if fname and fname.group(1).split("::")[-1] not in _NOT_FUNCTIONS:
                    qualified = fname.group(1)
                    parts = qualified.split("::")
                    first = stmt + len(raw) - len(raw.lstrip())
                    writes: Dict[str, List[str]] = {}
                    for name, form in _writes(blanked[i + 1:close]):
                        if form not in writes.setdefault(name, []):
                            writes[name].append(form)
                    functions.append({
                        "name": qualified,
                        "owner": parts[-2] if len(parts) > 1 else owner,
                        "line": line_of(first), "end_line": line_of(close),
                        "writes": writes,
                        "lines": _function_lines(text, first, close + 1)})
                    stmt = close + 1
                # anything else (an initializer, an enum body) belongs to
                # the statement it is in, which goes on to its ';'
                i = close + 1
                continue
            i += 1

    scan(0, len(blanked), None)
    return members, functions


# ============ LLM PURPOSE SUMMARIES ============

def _validate_purpose(raw) -> Tuple[Optional[dict], Optional[str]]:
    """call_agent validator: a reply with a 'purpose' string over 10
    chars, or a reason that triggers a corrective retry."""
    if isinstance(raw, dict) and isinstance(raw.get("purpose"), str) \
            and len(raw["purpose"].strip()) > 10:
        return {"purpose": raw["purpose"].strip()}, None
    return None, 'expected {"purpose": "<one sentence>"}'


def llm_purpose(model: str, file_path: str, text: str) -> Optional[str]:
    """A one-sentence purpose for the file, from its first 120 lines, or
    None when every attempt fails. Clipped at 500 chars; the pack clips
    further."""
    snippet = "\n".join(text.split("\n")[:120])
    result = call_agent(model, SUMMARY_PROMPT,
                        f"FILE: {file_path}\n\n{snippet}", TEMPERATURE_RETRY,
                        validate=_validate_purpose)
    if result.get("verdict") == "PARSE_FAILURE":
        return None
    return clip(result["purpose"], 500)  # presentation clips further


# ============ INDEX BUILD ============

_SKIP_DIRS = {".git", "build", ".venv", "__pycache__", "node_modules"}
_SKIP_DIR_PREFIXES = ("build-", "cmake-build-")


def _skipped(rel_parts) -> bool:
    """Whether a path relative to the target root lies under a VCS, build,
    virtualenv or cache directory. Only the target's own directories
    count, so a checkout under a 'build' directory still indexes."""
    return any(p in _SKIP_DIRS or p.startswith(_SKIP_DIR_PREFIXES)
               for p in rel_parts[:-1])


def _git_source(root: Path) -> Tuple[Optional[str], Optional[bool]]:
    """(commit, dirty) of the indexed checkout, or (None, None) when it is
    not a git work tree. Records which tree the pack describes; only
    tracked changes count as dirty."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain",
             "--untracked-files=no"],
            capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return commit, bool(status.strip())


def _git_blobs(root: Path, rels: List[str]) -> Dict[str, str]:
    """Each file's git blob id, as git would store its current content
    (line-ending conversion and clean filters applied), so it matches the
    'index' lines of diffs made from this tree. {} when git fails."""
    if not rels:
        return {}
    try:
        ids = subprocess.run(
            ["git", "-C", str(root), "hash-object", "--stdin-paths"],
            input="\n".join(rels) + "\n", capture_output=True, text=True,
            check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return {}
    return dict(zip(rels, ids)) if len(ids) == len(rels) else {}


def build_index(target_root: str, use_llm: bool = True) -> dict:
    """Walk the target repo and harvest its context index: per file the
    purpose, layer and git blob id; C typedefs; numeric constants; queued
    connection call sites; struct and class data members, and the
    functions that assign them (harvest_definitions); and the commit and
    dirty flag of the tree.
    Purposes come from the summary model (cached) or, with
    use_llm=False, from each file's first prose comment. Build, docs and
    CI files get a path-derived hint and layer 'meta'. Not saved; see
    save_index."""
    root = Path(target_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"ERROR: target repo not found: {root}")

    summary_model = MODELS["auto_engineer"]
    source_commit, source_dirty = _git_source(root)
    index = {
        "index_version": None,
        "source_commit": source_commit,
        "source_dirty": source_dirty,
        "llm_summaries": use_llm,
        "summary_model": summary_model if use_llm else None,
        "summary_prompt_version": SUMMARY_PROMPT_VERSION if use_llm else None,
        "files": [],
        "types": [],
        "constants": [],
        "callsites": [],  # queued-connection call sites
        "fields": [],     # struct/class data members
        "functions": [],  # function definitions that assign members
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
        digest = _file_digest(path)

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
            "purpose": clip(purpose or "", PURPOSE_LIMIT),
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
        for cs in harvest_callsites(text, rel):
            index["callsites"].append(cs)
        if path.suffix != ".qml":
            members, functions = harvest_definitions(text)
            index["fields"] += [dict(m, file=rel) for m in members]
            index["functions"] += [dict(f, file=rel) for f in functions]

    index["types"] = list(seen_types.values())
    index["constants"] = list(seen_consts.values())

    # A bare assignment writes a member only in a method of the member's
    # class (a header can declare the class its .cpp defines methods of);
    # keep only the functions that write some member.
    owned: Dict[str, set] = {}
    for m in index["fields"]:
        owned.setdefault(m["owner"], set()).add(m["name"])
    writers = []
    for f in index["functions"]:
        mine = owned.get(f["owner"], set())
        f["writes"] = {name: forms for name, forms in
                       ((n, [x for x in fs if x != "bare" or n in mine])
                        for n, fs in f["writes"].items()) if forms}
        if f["writes"]:
            writers.append(f)
    index["functions"] = writers

    # Blob ids let retrieval check that a diff's base is this tree.
    blobs = (_git_blobs(root, [f["path"] for f in index["files"]])
             if source_commit else {})
    for f in index["files"]:
        if f.get("layer") is None:
            f["layer"] = identify_layer(f["path"])
        f["blob"] = blobs.get(f["path"])

    return index


def _cache_path() -> Path:
    """The summary cache's path: CACHE_PATH, next to this module."""
    return CACHE_PATH


def _load_cache() -> dict:
    """The summary cache, or {} if it is missing or unreadable. The cache
    only saves model calls, so a corrupt file warns and is rebuilt."""
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        cache = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(cache, dict):
            return cache
        reason = f"a JSON {type(cache).__name__}, expected an object"
    except (OSError, ValueError) as exc:
        reason = f"{type(exc).__name__}: {exc}"
    print(f"WARNING: summary cache {p} is unreadable ({reason}); "
          "starting empty, it will be rewritten.", file=sys.stderr)
    return {}


def _save_cache(cache: dict) -> None:
    """Write the whole summary cache; called after every new summary, so
    an interrupted index run keeps what it paid for."""
    _cache_path().write_text(json.dumps(cache, indent=2), encoding="utf-8")


def save_index(index: dict, path: Optional[Path] = None) -> Path:
    """Stamp index_version with the UTC time and write the index to path,
    by default CONTEXT_PATH next to this module, which debates read
    unless given an index file (corpus fixtures keep their own). Returns
    the path written."""
    index["index_version"] = (
        f"idx_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    out = Path(path) if path else CONTEXT_PATH
    out.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return out
