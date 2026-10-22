"""Debate orchestration — the loop, guardrail application, judging,
and decision-record persistence."""

import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from adjudication import (demote_hedged_blockers, derive_verdict,
                          normalize_agent_output)
from agent_client import call_agent, failure_result
from config import (MAX_DEBATE_ROUNDS, MODELS, NUM_CTX, REVIEWER_HEADER_PROMPT,
                    REVIEWER_IMPL_PROMPT, TEMPERATURE_EXPLORATION,
                    TEMPERATURE_RETRY)
from file_metadata import get_layer_constraints, identify_layer
from repo_context import CONTEXT_PATH, PACK_FORMAT_VERSION, build_context_pack
from reviewer_prompt import PROMPT_VERSION, AUTO_ENGINEER_PROMPT

# ============ TRANSCRIPT TEMPLATES ============
# Model-facing text. Editing any of these is a prompt edit: bump
# PROMPT_VERSION. All of them feed the prompt_fingerprint in each record.
CONTEXT_CHAR_LIMIT = 8000

STATIC_TEMPLATE = """
CODE DIFF:
----------
{diff}

CODE CONTEXT:
-------------
{context}
"""

# NEW: retrieved repo context section. Model-facing — part of the
# v5-context-pack prompt change.
REPO_CONTEXT_TEMPLATE = """
REPO CONTEXT (verified facts extracted from the indexed source —
ground truth where it conflicts with inference from the diff alone):
--------------------------------------------------------------------
{pack}
END REPO CONTEXT.
"""

TRANSCRIPT_TEMPLATE = """
QTTUNE PROPOSAL FOR DEBATE
==========================
{proposal}
{static_section}
RESPOND WITH JSON ONLY using your role specification.

[DEBATE ROUND {round_num}]"""

FEEDBACK_TEMPLATE = """{proposal}

REVISE ADDRESSING:
- Reviewer blockers: {blockers}
- Engineer concerns: {concerns}"""

AGENT_FAILURE_VERDICT = "AGENT_FAILURE - MANUAL_REVIEW_REQUIRED"

# A path-like token with at least one directory and a file extension,
# e.g. 'core/src/x.cpp'. Rejects prose such as 'File/layer:'.
_PATH_TOKEN = re.compile(r"(?:[\w.-]+/)+[\w-]+\.[A-Za-z]{1,4}\b")
_CONTEXT_PATH_SCAN_LINES = 20


def extract_file_path(code_diff: str = "", code_context: str = "") -> str:
    """Best-effort path extraction for layer identification.
    Checks diff headers ('+++ b/...') first, then path tokens inside '//'
    comment lines near the top of the context.
    Known limitation: multi-file diffs yield only the first file's layer."""
    if code_diff:
        for line in code_diff.split('\n'):
            if line.startswith('+++ b/'):
                return line.replace('+++ b/', '').strip()
    if code_context:
        for line in code_context.split('\n')[:_CONTEXT_PATH_SCAN_LINES]:
            stripped = line.strip()
            if stripped.startswith('//'):
                m = _PATH_TOKEN.search(stripped[2:])
                if m:
                    return m.group(0)
    return ""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prompt_fingerprint(*parts: str) -> str:
    """Hash of every model-facing template actually used. Catches prompt
    drift that PROMPT_VERSION misses (templates outside reviewer_prompt.py,
    layer notes). Templates only, never text derived from the reviewed
    input, so runs of one prompt on different diffs share a fingerprint."""
    return _sha256("\x1e".join(parts))[:16]


def _is_failure(agent_out: dict) -> bool:
    return agent_out.get("verdict") == "PARSE_FAILURE"


def _load_repo_index(path: Optional[Path] = None) -> dict:
    """Load the checked-in context pack from next to repo_context.py, so
    retrieval works from any working directory. Fail visible, not fatal:
    a missing/corrupt index yields {'_load_error': ...}; the debate then
    proceeds WITHOUT retrieval, warns on stderr, and records the reason."""
    path = path or CONTEXT_PATH
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"_load_error": f"{type(exc).__name__}: {exc}"}


def _retrieve_pack(code_diff: str) -> Tuple[str, dict]:
    """(pack_text, pack_report) for the diff. Never raises: retrieval is
    an aid, so a missing, corrupt or malformed index degrades the debate
    to no retrieval, with the reason in report['error']."""
    repo_index = _load_repo_index()
    if "_load_error" in repo_index:
        return "", {"error": repo_index["_load_error"]}
    try:
        return build_context_pack(code_diff, repo_index)
    except Exception as exc:  # malformed index content, e.g. an entry without "name"
        return "", {"error": f"malformed index: {type(exc).__name__}: {exc}"}


def run_debate(proposal: str, code_diff: str = "", code_context: str = "",
               header_artifact: bool = False) -> dict:
    """Orchestrates the full debate loop. Returns structured decision
    with audit trail. header_artifact selects the header-scoped reviewer
    prompt (interface definitions) instead of implementation standards.

    NOTE (2026-10-09): the transcript is re-rendered from the CURRENT
    proposal each round, so REVISE ADDRESSING feedback is actually visible
    to both agents. Previously the base transcript was frozen before the
    loop — rounds 2+ were blind resamples, not debate. Archived records
    predate this fix; see ADR-0002 erratum.

    NOTE (2026-10-13): the transcript now includes a retrieved repo
    context pack (repo_context.json) when the diff matches indexed files.
    Retrieval failure is non-fatal and recorded in the decision record.
    PROMPT_VERSION v5-context-pack.
    """
    debate_id = (f"debate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                 f"_{uuid.uuid4().hex[:6]}")
    original_proposal = proposal

    reviewer_prompt = (REVIEWER_HEADER_PROMPT if header_artifact
                       else REVIEWER_IMPL_PROMPT)

    # ============ CONTEXT PACK RETRIEVAL ============
    pack_text, pack_report = _retrieve_pack(code_diff)
    retrieval_error = pack_report.get("error")
    if retrieval_error:
        print(f"WARNING: repo context retrieval unavailable "
              f"({retrieval_error}); debating without it.", file=sys.stderr)
    # The record keeps the exact pack the agents saw: repo_context.json is
    # overwritten on every re-index, so this is the only surviving copy.
    pack_report["sha256"] = _sha256(pack_text) if pack_text else None
    pack_report["text"] = pack_text
    if pack_text:
        repo_context_section = REPO_CONTEXT_TEMPLATE.format(pack=pack_text)
    else:
        repo_context_section = ""

    # Static transcript sections — built once, they never change.
    static_section = STATIC_TEMPLATE.format(
        diff=code_diff or '(no diff attached)',
        context=(code_context[:CONTEXT_CHAR_LIMIT] if code_context
                 else '(none provided)'))

    file_path = extract_file_path(code_diff, code_context)
    layer = identify_layer(file_path) if file_path else None
    layer_note = get_layer_constraints(layer) if layer else ""
    if repo_context_section:
        static_section = f"{static_section}{repo_context_section}"
    if layer_note:
        static_section = f"{static_section}\n{layer_note}\n"

    def render_transcript(current_proposal: str, round_num: int) -> str:
        """Full per-round transcript. Called EVERY round so the agents
        see the revised proposal (prior critiques included)."""
        return TRANSCRIPT_TEMPLATE.format(
            proposal=current_proposal, static_section=static_section,
            round_num=round_num)

    def validate_reviewer(raw):
        return normalize_agent_output(raw, "reviewer")

    def validate_engineer(raw):
        return normalize_agent_output(raw, "engineer")

    round_history: List[dict] = []
    final_verdict = "CONVERGENCE_FAILURE - CONFLICTING_CRITERIA"
    agent_failures: List[str] = []

    for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
        transcript = render_transcript(proposal, round_num)
        temperature = (TEMPERATURE_EXPLORATION if round_num == 1
                       else TEMPERATURE_RETRY)

        # Both agents critique the same transcript; they do not see
        # each other's responses until the judge feeds feedback back
        telemetry = {"reviewer": [], "auto_engineer": []}
        reviewer = call_agent(MODELS["code_reviewer"], reviewer_prompt,
                              transcript, temperature, validate=validate_reviewer,
                              telemetry=telemetry["reviewer"])
        if _is_failure(reviewer):
            # The round cannot be judged either way; don't spend another
            # (possibly 30-minute) failing call on the engineer.
            engineer = failure_result("not called: reviewer failed this round")
        else:
            engineer = call_agent(MODELS["auto_engineer"], AUTO_ENGINEER_PROMPT,
                                  transcript, temperature,
                                  validate=validate_engineer,
                                  telemetry=telemetry["auto_engineer"])

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
            "telemetry": telemetry,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # ============ FAIL CLOSED on unusable agent output ============
        for role, out in (("reviewer", reviewer), ("auto_engineer", engineer)):
            if _is_failure(out):
                agent_failures.append(
                    f"round {round_num} {role}: "
                    f"{out.get('failure_reason', 'unknown')}")
        if agent_failures:
            final_verdict = AGENT_FAILURE_VERDICT
            break

        # ============ JUDGE LOGIC (Rule-Based, Not Model) ============
        reviewer_v = derive_verdict(reviewer, "questions")
        engineer_v = derive_verdict(engineer, "concerns")
        reviewer_blockers = reviewer.get("blockers", []) or []
        engineer_concerns = ((engineer.get("concerns", []) or []) +
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

        # Feed critiques back: proposal grows, next round's transcript
        # re-renders from it — this is the debate actually functioning
        proposal = FEEDBACK_TEMPLATE.format(
            proposal=proposal,
            blockers='; '.join(str(b) for b in reviewer_blockers),
            concerns='; '.join(str(c) for c in engineer_concerns))

    inputs = {
        "proposal": proposal,  # final, feedback-grown (archived meaning)
        "original_proposal": original_proposal,
        "header_artifact": header_artifact,
        "file_path": file_path or None,
        "layer": layer,
        "diff_sha256": _sha256(code_diff) if code_diff else None,
        "diff_chars": len(code_diff),
        "context_sha256": _sha256(code_context) if code_context else None,
        "context_chars": len(code_context),
        "context_truncated": len(code_context) > CONTEXT_CHAR_LIMIT,
    }
    run_settings = {
        "temperature_exploration": TEMPERATURE_EXPLORATION,
        "temperature_retry": TEMPERATURE_RETRY,
        "num_ctx": NUM_CTX,
        "context_char_limit": CONTEXT_CHAR_LIMIT,
        "repo_context_pack": pack_report,
        "prompt_fingerprint": _prompt_fingerprint(
            reviewer_prompt, AUTO_ENGINEER_PROMPT, STATIC_TEMPLATE,
            TRANSCRIPT_TEMPLATE, FEEDBACK_TEMPLATE, layer_note,
            # the pack's template and format, not its input-derived text
            REPO_CONTEXT_TEMPLATE + PACK_FORMAT_VERSION if pack_text else ""),
    }
    decision_record = _save_decision_record(
        debate_id, inputs, final_verdict, round_history, run_settings,
        agent_failures)

    last = round_history[-1]
    result = {
        "debate_id": debate_id,
        "final_verdict": final_verdict,
        "rounds_completed": len(round_history),
        "decision_record_path": str(decision_record),
        "critique_summary": {
            # Summed over rounds: a blocker repeated each round counts each time.
            "total_blockers": sum(
                len(h["reviewer"].get("blockers", []) or [])
                for h in round_history),
            "total_concerns": sum(
                len(h["auto_engineer"].get("concerns", []) or [])
                for h in round_history),
            "final_round_blockers": len(last["reviewer"].get("blockers", []) or []),
            "final_round_concerns": len(
                last["auto_engineer"].get("concerns", []) or []),
        },
    }
    if agent_failures:
        result["agent_failures"] = agent_failures
    if retrieval_error:
        result["retrieval_error"] = retrieval_error
    return result


def _save_decision_record(debate_id: str, inputs: dict, verdict: str,
                           round_history: List[dict], run_settings: dict,
                           agent_failures: List[str]) -> Path:
    """ADR-style artifact for coach pipeline."""
    record = {
        "metadata": {
            "debate_id": debate_id,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "prompt_version": PROMPT_VERSION,
            "models_used": MODELS,
            "max_rounds": MAX_DEBATE_ROUNDS,
            **run_settings,
        },
        "inputs": inputs,
        "outputs": {"final_verdict": verdict, "round_history": round_history,
                    "agent_failures": agent_failures},
        "audit_trail": {
            "artifact_type": "decision_record",
            "intended_consumer": "coach_agent",
            "validation_method": "golden_test_suite",
        },
    }
    output_dir = Path("coach_artifacts")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"decision_{debate_id}.json"
    output_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return output_file
