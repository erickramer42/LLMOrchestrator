"""Debate orchestration — the loop, guardrail application, judging,
and decision-record persistence. Also the round-1 reviewer measurement
mode, which sends the reviewer the same first transcript as a debate."""

import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from adjudication import (JUDGE_VERSION, convergence_verdict,
                          demote_hedged_blockers, derive_verdict,
                          normalize_agent_output)
from agent_client import call_agent, failure_result
from config import (MAX_DEBATE_ROUNDS, MODELS, NUM_CTX, NUM_PREDICT,
                    REVIEWER_HEADER_PROMPT, REVIEWER_IMPL_PROMPT,
                    TEMPERATURE_EXPLORATION, TEMPERATURE_RETRY)
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

# Retrieved repo context. The pack is a snapshot of the indexed tree, which
# need not match the code before or after the diff, so the diff wins
# (code review 2026-10-21, finding 1; v6).
REPO_CONTEXT_TEMPLATE = """
REPO CONTEXT (a snapshot of the indexed source tree; it may not match
the code before or after this diff. The CODE DIFF is authoritative for
every file and symbol it touches: where they disagree, trust the diff.
File purposes are machine-written summaries, not verified facts):
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
# A measurement judges nothing, so its record must never read as a merge
# decision, approving or otherwise.
MEASUREMENT_VERDICT = "NOT_ADJUDICATED - ROUND1_MEASUREMENT"

DEBATE_MODE = "debate"
MEASUREMENT_MODE = "round1_reviewer"

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


def _new_id(kind: str) -> str:
    """Timestamp plus a random suffix, so same-second runs don't collide."""
    return (f"{kind}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            f"_{uuid.uuid4().hex[:6]}")


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


class _Setup(NamedTuple):
    """What every transcript of one review is built from. Shared by
    run_debate and run_round1_review, so a measurement sends the reviewer
    exactly the prompt a debate's first call does."""
    reviewer_prompt: str
    static_section: str
    pack_text: str
    pack_report: dict
    file_path: str
    layer: Optional[str]
    layer_note: str


def _prepare(code_diff: str, code_context: str, header_artifact: bool) -> _Setup:
    """Retrieve the context pack and build the static transcript sections.
    header_artifact selects the header-scoped reviewer prompt (interface
    definitions) instead of implementation standards."""
    reviewer_prompt = (REVIEWER_HEADER_PROMPT if header_artifact
                       else REVIEWER_IMPL_PROMPT)

    # ============ CONTEXT PACK RETRIEVAL ============
    pack_text, pack_report = _retrieve_pack(code_diff)
    if pack_report.get("error"):
        print(f"WARNING: repo context retrieval unavailable "
              f"({pack_report['error']}); continuing without it.",
              file=sys.stderr)
    # The record keeps the exact pack the agents saw: repo_context.json is
    # overwritten on every re-index, so this is the only surviving copy.
    pack_report["sha256"] = _sha256(pack_text) if pack_text else None
    pack_report["text"] = pack_text

    # Static transcript sections — built once, they never change.
    static_section = STATIC_TEMPLATE.format(
        diff=code_diff or '(no diff attached)',
        context=(code_context[:CONTEXT_CHAR_LIMIT] if code_context
                 else '(none provided)'))

    file_path = extract_file_path(code_diff, code_context)
    layer = identify_layer(file_path) if file_path else None
    layer_note = get_layer_constraints(layer) if layer else ""
    if pack_text:
        static_section += REPO_CONTEXT_TEMPLATE.format(pack=pack_text)
    if layer_note:
        static_section = f"{static_section}\n{layer_note}\n"
    return _Setup(reviewer_prompt, static_section, pack_text, pack_report,
                  file_path, layer, layer_note)


def _render_transcript(proposal: str, static_section: str, round_num: int) -> str:
    """Full per-round transcript. Rendered EVERY round so the agents see
    the revised proposal (prior critiques included)."""
    return TRANSCRIPT_TEMPLATE.format(
        proposal=proposal, static_section=static_section, round_num=round_num)


def _validate_reviewer(raw):
    return normalize_agent_output(raw, "reviewer")


def _validate_engineer(raw):
    return normalize_agent_output(raw, "engineer")


def _record_inputs(setup: _Setup, proposal: str, original_proposal: str,
                   code_diff: str, code_context: str,
                   header_artifact: bool) -> dict:
    return {
        "proposal": proposal,  # final, feedback-grown (archived meaning)
        "original_proposal": original_proposal,
        "header_artifact": header_artifact,
        "file_path": setup.file_path or None,
        "layer": setup.layer,
        "diff_sha256": _sha256(code_diff) if code_diff else None,
        "diff_chars": len(code_diff),
        "context_sha256": _sha256(code_context) if code_context else None,
        "context_chars": len(code_context),
        "context_truncated": len(code_context) > CONTEXT_CHAR_LIMIT,
    }


def _run_settings(setup: _Setup, mode: str, max_rounds: int) -> dict:
    """Sampling settings and prompt provenance. A measurement's
    fingerprint covers the engineer's templates too, though it never sends
    them: the fingerprint names the prompt revision, so measurement
    samples group with the debates of the same revision, and `mode` tells
    them apart."""
    return {
        "mode": mode,
        "max_rounds": max_rounds,
        "temperature_exploration": TEMPERATURE_EXPLORATION,
        "temperature_retry": TEMPERATURE_RETRY,
        "num_ctx": NUM_CTX,
        "num_predict": NUM_PREDICT,
        "context_char_limit": CONTEXT_CHAR_LIMIT,
        "repo_context_pack": setup.pack_report,
        "prompt_fingerprint": _prompt_fingerprint(
            setup.reviewer_prompt, AUTO_ENGINEER_PROMPT, STATIC_TEMPLATE,
            TRANSCRIPT_TEMPLATE, FEEDBACK_TEMPLATE, setup.layer_note,
            # the pack's template and format, not its input-derived text
            REPO_CONTEXT_TEMPLATE + PACK_FORMAT_VERSION if setup.pack_text else ""),
    }


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
    debate_id = _new_id("debate")
    original_proposal = proposal
    setup = _prepare(code_diff, code_context, header_artifact)

    round_history: List[dict] = []
    agent_failures: List[str] = []

    for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
        transcript = _render_transcript(proposal, setup.static_section, round_num)
        temperature = (TEMPERATURE_EXPLORATION if round_num == 1
                       else TEMPERATURE_RETRY)

        # Both agents critique the same transcript; they do not see
        # each other's responses until the judge feeds feedback back
        telemetry = {"reviewer": [], "auto_engineer": []}
        reviewer = call_agent(MODELS["code_reviewer"], setup.reviewer_prompt,
                              transcript, temperature, validate=_validate_reviewer,
                              telemetry=telemetry["reviewer"])
        if _is_failure(reviewer):
            # The round cannot be judged either way; don't spend another
            # (possibly 30-minute) failing call on the engineer.
            engineer = failure_result("not called: reviewer failed this round")
        else:
            engineer = call_agent(MODELS["auto_engineer"], AUTO_ENGINEER_PROMPT,
                                  transcript, temperature,
                                  validate=_validate_engineer,
                                  telemetry=telemetry["auto_engineer"])

        # ============ GUARDRAIL: hedge demotion (before storing) ============
        reviewer, rev_demoted = demote_hedged_blockers(reviewer, "questions")
        engineer, eng_demoted = demote_hedged_blockers(engineer, "concerns")
        hedge_stats = {"reviewer_demoted": rev_demoted,
                       "engineer_demoted": eng_demoted}

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
        converged = convergence_verdict(reviewer_v, engineer_v)
        if converged:
            final_verdict = converged
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

    decision_record = _save_decision_record(
        debate_id,
        _record_inputs(setup, proposal, original_proposal, code_diff,
                       code_context, header_artifact),
        final_verdict, round_history,
        _run_settings(setup, DEBATE_MODE, MAX_DEBATE_ROUNDS), agent_failures)

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
    if setup.pack_report.get("error"):
        result["retrieval_error"] = setup.pack_report["error"]
    return result


def run_round1_review(proposal: str, code_diff: str = "", code_context: str = "",
                      header_artifact: bool = False) -> dict:
    """One reviewer call on the transcript a debate's first round sends,
    for measurements, which score round-1 reviewer blockers. The round-1
    reviewer never sees the engineer, so this samples the same output as
    a debate's first call without running the rest of the debate.

    Retries and hedge demotion work as in a debate; nothing is judged. The
    record is coach_artifacts/measurement_<id>.json, with mode
    round1_reviewer, verdict MEASUREMENT_VERDICT (AGENT_FAILURE_VERDICT if
    every attempt failed), and no engineer entry in its one round."""
    measurement_id = _new_id("round1")
    setup = _prepare(code_diff, code_context, header_artifact)

    telemetry = {"reviewer": []}
    reviewer = call_agent(MODELS["code_reviewer"], setup.reviewer_prompt,
                          _render_transcript(proposal, setup.static_section, 1),
                          TEMPERATURE_EXPLORATION, validate=_validate_reviewer,
                          telemetry=telemetry["reviewer"])
    reviewer, demoted = demote_hedged_blockers(reviewer, "questions")
    agent_failures = ([f"round 1 reviewer: "
                       f"{reviewer.get('failure_reason', 'unknown')}"]
                      if _is_failure(reviewer) else [])
    verdict = AGENT_FAILURE_VERDICT if agent_failures else MEASUREMENT_VERDICT
    round_history = [{
        "round": 1,
        "reviewer": reviewer,
        "hedge_demotions": {"reviewer_demoted": demoted},
        "telemetry": telemetry,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]
    record = _save_decision_record(
        measurement_id,
        _record_inputs(setup, proposal, proposal, code_diff, code_context,
                       header_artifact),
        verdict, round_history, _run_settings(setup, MEASUREMENT_MODE, 1),
        agent_failures)

    result = {
        "measurement_id": measurement_id,
        "final_verdict": verdict,
        "record_path": str(record),
        "blockers": len(reviewer.get("blockers", []) or []),
        "attempts": len(telemetry["reviewer"]),
    }
    if agent_failures:
        result["agent_failures"] = agent_failures
    if setup.pack_report.get("error"):
        result["retrieval_error"] = setup.pack_report["error"]
    return result


# mode -> (file name prefix, artifact type, intended consumer)
_RECORD_KINDS = {
    DEBATE_MODE: ("decision", "decision_record", "coach_agent"),
    MEASUREMENT_MODE: ("measurement", "measurement_record", "eval_harness.round1"),
}


def _save_decision_record(record_id: str, inputs: dict, verdict: str,
                           round_history: List[dict], run_settings: dict,
                           agent_failures: List[str]) -> Path:
    """ADR-style artifact for coach pipeline. A measurement is saved as
    measurement_<id>.json, so nothing reads it as a merge decision. Both
    kinds keep the id under metadata.debate_id, so record readers need no
    branch."""
    prefix, artifact_type, consumer = _RECORD_KINDS[run_settings["mode"]]
    record = {
        "metadata": {
            "debate_id": record_id,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "prompt_version": PROMPT_VERSION,
            "judge_version": JUDGE_VERSION,
            "models_used": MODELS,
            **run_settings,
        },
        "inputs": inputs,
        "outputs": {"final_verdict": verdict, "round_history": round_history,
                    "agent_failures": agent_failures},
        "audit_trail": {
            "artifact_type": artifact_type,
            "intended_consumer": consumer,
            "validation_method": "golden_test_suite",
        },
    }
    output_dir = Path("coach_artifacts")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{prefix}_{record_id}.json"
    output_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return output_file
