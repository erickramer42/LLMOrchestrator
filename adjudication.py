"""Deterministic adjudication: verdict derivation + hedge demotion guardrail.
Pure functions — no I/O, no LLM calls. Fully unit-testable in CI."""

import re


# ============ VERDICT DERIVATION ============

def derive_verdict(agent_out: dict, concern_key: str = "questions") -> str:
    """Merge decision from agent CONTENT, never the model's self-reported label.
    concern_key: 'questions' (reviewer) or 'concerns'/'questions' (engineer)."""
    if not agent_out or agent_out.get("verdict") == "PARSE_FAILURE":
        return "reject"
    blockers = agent_out.get("blockers", []) or []
    open_items = (agent_out.get(concern_key, []) or
                  agent_out.get("questions", []) or [])
    if blockers:
        return "reject"
    if open_items:
        return "conditional"
    return "approve"


# ============ HEDGE LANGUAGE DEMOTION ============

HEDGE_PATTERNS = re.compile(
    r"\b(may|might|could|possibly|potentially|speculative|"
    r"needs? verification|unverifiable|suspected|appears to|"
    r"seems to|likely|uncertain|check if|need to confirm|is it|"
    r"doesn't appear to|may cause|risk of|might introduce)\b",
    re.IGNORECASE)


def demote_hedged_blockers(agent_out: dict, concern_key: str = "questions") -> dict:
    """Guardrail: speculative/hedged text in blockers becomes a question.
    Enforces the taxonomy rule: a blocker must be a DEMONSTRABLE violation."""
    if not agent_out or agent_out.get("verdict") == "PARSE_FAILURE":
        return agent_out

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

    return out
