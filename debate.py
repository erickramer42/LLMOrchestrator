"""Debate orchestration — the loop, guardrail application, judging,
and decision-record persistence."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from adjudication import demote_hedged_blockers, derive_verdict
from agent_client import call_agent
from config import (MAX_DEBATE_ROUNDS, MODELS, REVIEWER_HEADER_PROMPT,
                    REVIEWER_IMPL_PROMPT, TEMPERATURE_EXPLORATION,
                    TEMPERATURE_RETRY)
from file_metadata import get_layer_constraints, identify_layer
from reviewer_prompt import PROMPT_VERSION, AUTO_ENGINEER_PROMPT


def extract_file_path(code_diff: str = "", code_context: str = "") -> str:
    """Best-effort path extraction for layer identification.
    Checks diff headers ('+++ b/...') first, then '// path' comment lines.
    Known limitation: multi-file diffs yield only the first file's layer."""
    if code_diff:
        for line in code_diff.split('\n'):
            if line.startswith('+++ b/'):
                return line.replace('+++ b/', '').strip()
    if code_context:
        for line in code_context.split('\n'):
            stripped = line.strip()
            if stripped.startswith('//') and '/' in stripped:
                return stripped  # whole line; identify_layer substring-searches
    return ""


def run_debate(proposal: str, code_diff: str = "", code_context: str = "",
               header_artifact: bool = False) -> dict:
    """Orchestrates the full debate loop. Returns structured decision
    with audit trail. header_artifact selects the header-scoped reviewer
    prompt (interface definitions) instead of implementation standards."""
    debate_id = f"debate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    reviewer_prompt = (REVIEWER_HEADER_PROMPT if header_artifact
                       else REVIEWER_IMPL_PROMPT)

    transcript_base = f"""
QTTUNE PROPOSAL FOR DEBATE
==========================
{proposal}

CODE DIFF:
----------
{code_diff or '(no diff attached)'}

CODE CONTEXT:
-------------
{code_context[:8000] if code_context else '(none provided)'}

RESPOND WITH JSON ONLY using your role specification.
"""

    file_path = extract_file_path(code_diff, code_context)
    if file_path:
        layer_note = get_layer_constraints(identify_layer(file_path))
        transcript_base = f"{transcript_base}\n\n{layer_note}\n"

    round_history: List[dict] = []
    final_verdict = "CONVERGENCE_FAILURE - CONFLICTING_CRITERIA"

    for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
        transcript = f"{transcript_base}\n\n[DEBATE ROUND {round_num}]"

        # Both agents critique the same transcript; they do not see
        # each other's responses until the judge feeds feedback back
        reviewer = call_agent(
            MODELS["code_reviewer"], reviewer_prompt, transcript,
            TEMPERATURE_EXPLORATION if round_num == 1 else TEMPERATURE_RETRY)

        engineer = call_agent(
            MODELS["auto_engineer"], AUTO_ENGINEER_PROMPT, transcript,
            TEMPERATURE_EXPLORATION if round_num == 1 else TEMPERATURE_RETRY)

        # ============ GUARDRAIL: hedge demotion (before storing) ============
        rev_before = len(reviewer.get("blockers", []) or [])
        eng_before = len(engineer.get("blockers", []) or [])
        reviewer = demote_hedged_blockers(reviewer, "questions")
        engineer = demote_hedged_blockers(engineer, "concerns")
        hedge_stats = {
            "reviewer_demoted": rev_before - len(reviewer.get("blockers", []) or []),
            "engineer_demoted": eng_before - len(engineer.get("blockers", []) or []),
        }

        round_history.append({
            "round": round_num,
            "reviewer": reviewer,
            "auto_engineer": engineer,
            "hedge_demotions": hedge_stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # ============ JUDGE LOGIC (Rule-Based, Not Model) ============
        reviewer_v = derive_verdict(reviewer, "questions")
        engineer_v = derive_verdict(engineer, "concerns")
        reviewer_blockers = reviewer.get("blockers", []) or []
        engineer_concerns = (engineer.get("concerns", []) +
                            (engineer.get("questions", []) or []))

        # Termination conditions
        if reviewer_v == "approve" and engineer_v in ("approve", "defer"):
            final_verdict = "APPROVED_FOR_MERGE"
            break
        if reviewer_v == "conditional" and engineer_v in ("approve", "defer"):
            final_verdict = "APPROVED_WITH_OPEN_QUESTIONS"
            break
        if round_num >= MAX_DEBATE_ROUNDS:
            final_verdict = "MAX_ROUNDS_EXCEEDED - MANUAL_REVIEW_REQUIRED"
            break

        # Feed critiques back for next iteration
        feedback = (f"- Reviewer blockers: {'; '.join(reviewer_blockers)}\n"
                    f"- Engineer concerns: {'; '.join(engineer_concerns)}")
        proposal = f"{proposal}\n\nREVISE ADDRESSING:\n{feedback}"

    decision_record = _save_decision_record(
        debate_id, proposal, final_verdict, round_history)

    return {
        "debate_id": debate_id,
        "final_verdict": final_verdict,
        "rounds_completed": len(round_history),
        "decision_record_path": str(decision_record),
        "critique_summary": {
            "total_blockers": sum(
                len(h["reviewer"].get("blockers", []) or [])
                for h in round_history),
            "total_concerns": sum(
                len(h["auto_engineer"].get("concerns", []) or [])
                for h in round_history),
        },
    }


def _save_decision_record(debate_id: str, proposal: str, verdict: str,
                          round_history: List[dict]) -> Path:
    """ADR-style artifact for coach pipeline."""
    record = {
        "metadata": {
            "debate_id": debate_id,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "prompt_version": PROMPT_VERSION,
            "models_used": MODELS,
            "max_rounds": MAX_DEBATE_ROUNDS,
        },
        "inputs": {"proposal": proposal},
        "outputs": {"final_verdict": verdict, "round_history": round_history},
        "audit_trail": {
            "artifact_type": "decision_record",
            "intended_consumer": "coach_agent",
            "validation_method": "golden_test_suite",
        },
    }
    output_dir = Path("coach_artifacts")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"decision_{debate_id}.json"
    output_file.write_text(json.dumps(record, indent=2))
    return output_file
