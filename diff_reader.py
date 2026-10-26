"""Unified-diff reading, shared by layer identification (debate.py),
retrieval and its index-base check (retrieval.py) and the evidence
check (adjudication.py). Pure: no I/O."""

import re
from typing import Dict, Iterator, List, Tuple

DEV_NULL = "/dev/null"

_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@(.*)")
# The path ends at a tab: git adds one after a path with spaces, diff -u
# a timestamp.
_FILE_HEADER = re.compile(r"^(?:---|\+\+\+) (?:[ab]/)?([^\t]*[^\t\s])")
# git's 'index <pre-image>..<post-image> [mode]' line
_BLOB_LINE = re.compile(r"^index ([0-9a-f]{7,64})\.\.[0-9a-f]{7,64}\b")


# An identifier token, and whether a name reads as code. Shared by the
# judge (claim-quote linkage, j8) and retrieval, which re-exports both.
IDENT = re.compile(r"\b[A-Za-z_]\w*\b")


def code_like(name: str) -> bool:
    """A name that reads as code, not an English word: snake_case,
    camelCase or PascalCase, or containing a digit."""
    return ("_" in name or any(c.isdigit() for c in name)
            or any(c.isupper() for c in name[1:]))


def read_diff(code_diff: str) -> Iterator[Tuple[str, str]]:
    """Each line of a unified diff as (tag, text):
    - '---' or '+++': a file header; text is the path without its a/ or
      b/ prefix, or '/dev/null' for an added or deleted file's other side;
    - '@@': a hunk header; text is what follows it (git's enclosing line);
    - ' ', '-' or '+': a context, removed or added line, without its marker.
    Other lines (diff --git, index, mode lines, '\\ No newline at end of
    file') are skipped.

    Inside a hunk, lines are counted by the header's lengths, so a removed
    line that starts with '--' is not taken for a file header. Outside one
    (a hand-written diff without hunk headers, or past a miscounted hunk),
    a line is read by its first character."""
    old_left = new_left = 0
    for line in code_diff.split("\n"):
        tag = line[:1]
        if old_left > 0 or new_left > 0:
            if tag == "\\":
                continue
            if tag in (" ", "", "-", "+"):  # "" is a context line stripped of its space
                if tag != "+":
                    old_left -= 1
                if tag != "-":
                    new_left -= 1
                yield tag or " ", line[1:]
                continue
            old_left = new_left = 0  # malformed hunk: read the line as a header
        hunk = _HUNK.match(line)
        if hunk:
            old_left = int(hunk.group(1) or 1)
            new_left = int(hunk.group(2) or 1)
            yield "@@", hunk.group(3)
            continue
        header = _FILE_HEADER.match(line)
        if header:
            yield line[:3], header.group(1)
        elif tag in (" ", "-", "+"):
            yield tag, line[1:]


def diff_paths(code_diff: str) -> List[str]:
    """The paths of the diff's '+++' headers, in order: each changed file
    as it reads after the change. A deleted file has none."""
    return [text for tag, text in read_diff(code_diff)
            if tag == "+++" and text != DEV_NULL]


def base_blobs(code_diff: str) -> Dict[str, str]:
    """Each changed file's git blob id before the change, keyed by its
    path before the change, as the diff abbreviates it (git's
    'index <before>..<after>' line). Only git diffs have one, and a file
    the diff adds has none. The line belongs to the '---' header that
    follows it within the same 'diff --git' block, so a binary file's
    line, which has no header, is dropped."""
    blobs: Dict[str, str] = {}
    pending = None
    for line in code_diff.split("\n"):
        if line.startswith("diff --git "):
            pending = None
            continue
        blob = _BLOB_LINE.match(line)
        if blob:
            pending = blob.group(1)
            continue
        header = _FILE_HEADER.match(line) if pending else None
        if header and line.startswith("---"):
            if header.group(1) != DEV_NULL:  # an added file has no base
                blobs[header.group(1)] = pending
            pending = None
    return blobs
