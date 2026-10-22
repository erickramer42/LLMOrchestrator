"""Deterministic adjudication: schema validation, verdict derivation and
hedge demotion. Pure functions: no I/O, no LLM calls. Fully unit-testable
in CI."""

import re
from typing import Optional, Tuple

# Stamped into every decision record: a judge change alters final verdicts
# and round counts without touching any prompt, so the prompt fingerprint
# cannot show it. j1 (until 2026-10-22) also required the engineer to have
# zero concerns and questions.
JUDGE_VERSION = "j2-no-blockers"


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


def normalize_agent_output(raw, role: str) -> Tuple[Optional[dict], Optional[str]]:
    """Validate a parsed agent reply against its role schema and coerce
    the arrays into lists of non-empty strings.

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
        items = (_coerce_item(v) for v in value)
        out[key] = [s for s in items
                    if s and s.lower().strip(" .") not in _PLACEHOLDER_ITEMS]
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
