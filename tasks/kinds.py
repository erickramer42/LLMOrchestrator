"""The task kinds: what a submitter sends, what a worker is told (the
instructions are model-facing: any edit bumps the kind's version), and the
shape a worker's answer must have. Pure: no I/O.
"""

from typing import List, Optional, Tuple

MAX_FINDINGS = 100
MAX_TEXT = 20_000
VERDICTS = ("supported", "refuted", "unclear")
CHECKED = ("supported", "refuted")  # verdicts that must quote the code

SECOND_READ = "second_read"
SECOND_READ_VERSION = "sr1"
SECOND_READ_INSTRUCTIONS = """\
Second read. Another reviewer raised the findings below about the code at
this task's commit. For each finding, decide from the code whether it holds.
Read the files listed under files: read each at its read_from path. Judge
only from those files.

Answer with submit_result, one item per finding:
  finding  the finding's index
  verdict  supported (the code shows the finding is right), refuted (the code
           shows it is wrong) or unclear (the listed files do not settle it)
  file     the path, as listed, of the file your quote is from
  quote    code copied exactly from that file: whole lines, the longest at
           least 8 characters that are not spaces
  reason   one plain sentence on what the quoted code shows

A supported or refuted item must quote the code that shows it. Its reason
must not hedge: no may, might, could, likely, possibly, seems to, appears to.
An item whose quote is not in that file, or whose reason hedges, comes back
once with the reason; after that it is reported as unverified. An unclear
item needs no quote.
"""


class PayloadError(ValueError):
    """A submission or an answer this kind cannot take; the message says why."""


def _text(value, name: str, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise PayloadError(f"{name} must be {'non-empty ' if required else ''}text")
    if len(value) > MAX_TEXT:
        raise PayloadError(f"{name} is over {MAX_TEXT} characters")
    return value


def second_read_payload(payload) -> dict:
    """{findings: [{claim, file, quote?, line?}], question?}, normalized."""
    if not isinstance(payload, dict):
        raise PayloadError("the payload must be an object")
    findings = payload.get("findings")
    if not isinstance(findings, list) or not findings:
        raise PayloadError("findings must be a non-empty list")
    if len(findings) > MAX_FINDINGS:
        raise PayloadError(f"{len(findings)} findings, over the {MAX_FINDINGS} limit")
    out = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            raise PayloadError(f"finding {i} must be an object")
        out.append({"claim": _text(f.get("claim"), f"finding {i}'s claim"),
                    "file": _text(f.get("file"), f"finding {i}'s file"),
                    "quote": _text(f.get("quote"), f"finding {i}'s quote", required=False),
                    "line": "" if f.get("line") is None else str(f["line"])[:200]})
    return {"findings": out,
            "question": _text(payload.get("question"), "question", required=False)}


def cited_paths(payload: dict) -> List[str]:
    return list(dict.fromkeys(f["file"] for f in payload["findings"]))


def second_read_item(item, findings: int) -> Tuple[Optional[dict], Optional[str]]:
    """(the item normalized, None), or (None, why it has the wrong shape)."""
    if not isinstance(item, dict):
        return None, "an item must be an object"
    n = item.get("finding")
    if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n < findings:
        return None, f"finding must be an index from 0 to {findings - 1}"
    verdict = item.get("verdict")
    if verdict not in VERDICTS:
        return None, f"verdict must be one of {', '.join(VERDICTS)}"
    fields = {}
    for name in ("file", "quote", "reason"):
        value = item.get(name, "")
        if not isinstance(value, str) or len(value) > MAX_TEXT:
            return None, f"{name} must be text under {MAX_TEXT} characters"
        fields[name] = value
    if verdict in CHECKED and not (fields["file"].strip() and fields["quote"].strip()
                                   and fields["reason"].strip()):
        return None, f"a {verdict} item needs a file, a quote and a reason"
    return {"finding": n, "verdict": verdict, **fields}, None


KINDS = {SECOND_READ: {"version": SECOND_READ_VERSION,
                       "instructions": SECOND_READ_INSTRUCTIONS,
                       "payload": second_read_payload, "cited": cited_paths,
                       "item": second_read_item}}
