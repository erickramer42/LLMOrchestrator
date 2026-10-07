#!/usr/bin/env python3
"""
QtTune Agent Tribunal — Hand-rolled multi-agent orchestration.

Architecture:
    PROPOSE -> CRITIQUE (reviewer + auto_engineer) -> N ROUNDS DEBATE
    -> RULE-BASED JUDGE -> DECISION_RECORD (JSON for coach consumption)

Key Decisions:
    - Rule-based judge (not model) for deterministic termination
    - Verdicts derived from content (blockers/questions), never the
      model's self-reported verdict label
    - JSON-mode enforced via Ollama format parameter; parse failures
      fail closed (reject)
    - Prompts imported from reviewer_prompt.py (single source of truth)
    - Golden tests call the reviewer directly (unit scope, no debate
      overhead, no coach_artifact pollution)

Author: Eric | License: MIT
"""

import json
import os
import time
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import List

from reviewer_prompt import (PROMPT_VERSION, FAILURE_SENTINEL,
                             AUTO_ENGINEER_PROMPT)

# ============ CONFIGURATION ============
OLLAMA_BASE_URL = "http://localhost:11434/api/chat"

MODELS = {
    "code_reviewer": "laguna-xs-2.1",
    "auto_engineer": "gemma4:12b",
}

MAX_DEBATE_ROUNDS = 3
NUM_CTX = 16384            # Validated by fp_rate_probe (5/5 clean)
REQUEST_TIMEOUT_S = 600    # Kept at 600s per probe p-latency discussion
TEMPERATURE_EXPLORATION = 0.7
TEMPERATURE_RETRY = 0.05

# Imports for reviewer prompt composition (avoids duplication)
from reviewer_prompt import REVIEWER_SYSTEM, IMPL_SCOPE_CLAUSE, HEADER_SCOPE_CLAUSE

REVIEWER_IMPL_PROMPT = REVIEWER_SYSTEM + IMPL_SCOPE_CLAUSE
REVIEWER_HEADER_PROMPT = REVIEWER_SYSTEM + HEADER_SCOPE_CLAUSE


# ============ VERDICT DERIVATION (module level, deterministic) ============

def derive_verdict(agent_out: dict, concern_key: str = "questions") -> str:
    """Merge decision from agent CONTENT, never the model's self-reported label.

    concern_key: 'questions' (reviewer) or 'concerns' (engineer).
    Rule: blockers block, questions/concerns do NOT block merge."""
    if not agent_out or agent_out.get("verdict") == "PARSE_FAILURE":
        return "reject"
    blockers = agent_out.get("blockers", []) or []
    open_items = (agent_out.get(concern_key, []) or
                  agent_out.get("questions", []) or [])
    if blockers:
        return "reject"  # must-fix before merge
    # Questions/concerns alone don't block — they're follow-up debt
    if open_items:
        return "conditional"  # merge-worthy but needs attention
    return "approve"


# ============ CORE ORCHESTRATION ============

def call_agent(model: str, system_prompt: str, transcript: str,
               temperature: float) -> dict:
    """Single agent turn with JSON-mode enforcement and retry logic.
    Returns FAILURE_SENTINEL on total failure (fail closed)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript},
    ]

    for attempt in range(3):
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature if attempt == 0 else TEMPERATURE_RETRY,
                "num_ctx": NUM_CTX,
            },
        }
        try:
            resp = requests.post(OLLAMA_BASE_URL, json=payload,
                                 timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            result = resp.json()
            return json.loads(result["message"]["content"])
        except json.JSONDecodeError:
            messages.append({"role": "user",
                            "content": "Invalid JSON. Reply with valid JSON only."})
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            print(f"    ({model} attempt {attempt}: {type(e).__name__}, retrying)")
            time.sleep(5)

    return dict(FAILURE_SENTINEL)


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

        round_history.append({
            "round": round_num,
            "reviewer": reviewer,
            "auto_engineer": engineer,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # ============ JUDGE LOGIC (Rule-Based, Not Model) ============
        reviewer_v = derive_verdict(reviewer, "questions")
        engineer_v = derive_verdict(engineer, "concerns")
        reviewer_blockers = reviewer.get("blockers", []) or []
        engineer_concerns = (engineer.get("concerns", []) +
                            (engineer.get("questions", []) or []))

        if reviewer_v == "approve" and engineer_v in ("approve", "defer"):
            final_verdict = "APPROVED_FOR_MERGE"
            break
        if reviewer_v == "conditional" and engineer_v in ("approve", "defer"):
            final_verdict = "APPROVED_WITH_OPEN_QUESTIONS"
            break
        if round_num >= MAX_DEBATE_ROUNDS:
            final_verdict = "MAX_ROUNDS_EXCEEDED - MANUAL_REVIEW_REQUIRED"
            break

        # Feed critiques back for the next round
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


# ============ GOLDEN TEST SUITE ============
# Tests the REVIEWER UNIT directly — no debate loop, no coach artifacts.

def run_golden_tests() -> dict:
    TEST_CASES = [
        {
            "name": "buffer_overflow_can_fd",
            "snippet": ('// core/src/frame_decode.cpp\n'
                        'void decode(const PASSTHRU_MSG* msg) {\n'
                        '    uint8_t buf[8];\n'
                        '    memcpy(buf, msg->Data, msg->DataSize);\n'
                        '}'),
            "expected_to_block": True,
            "header": False,
        },
        {
            "name": "abi_type_leak",
            "snippet": ('// core/include/qttune/session.h (public C ABI header)\n'
                        '#include <vector>\n'
                        '#include <string>\n'
                        'extern "C" std::vector<std::string> '
                        'qttune_get_session_names(qttune_session_t* s);'),
            "expected_to_block": True,
            "header": True,
        },
        {
            "name": "clean_abi_pattern",
            "snippet": ('// core/include/qttune/init.h\n'
                        '#pragma once\n'
                        '#ifdef __cplusplus\nextern "C" {\n#endif\n'
                        'typedef struct qttune_ctx qttune_ctx;\n'
                        'int qttune_init(qttune_ctx** out);\n'
                        'int qttune_shutdown(qttune_ctx* ctx);\n'
                        '#ifdef __cplusplus\n}\n#endif'),
            "expected_to_block": False,
            "header": True,
        },
    ]

    results = []
    for tc in TEST_CASES:
        prompt = (REVIEWER_HEADER_PROMPT if tc["header"]
                 else REVIEWER_IMPL_PROMPT)
        out = call_agent(MODELS["code_reviewer"], prompt, tc["snippet"],
                         TEMPERATURE_RETRY)
        detected = bool(out.get("blockers"))
        passed = detected == tc["expected_to_block"]
        results.append({"test_name": tc["name"],
                        "expected_to_block": tc["expected_to_block"],
                        "detected": detected, "test_passed": passed})

    summary = {"total_tests": len(TEST_CASES),
               "passed": sum(r["test_passed"] for r in results),
               "failed": len(TEST_CASES) - sum(r["test_passed"] for r in results),
               "individual_results": results}

    test_log = Path("gold_tests") / f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    test_log.parent.mkdir(exist_ok=True)
    test_log.write_text(json.dumps(summary, indent=2))

    print(f"\n{'='*50}")
    print(f"Golden Tests: {summary['passed']}/{summary['total_tests']} passed")
    print(f"{'='*50}")
    for r in results:
        print(f"  {'PASS' if r['test_passed'] else 'FAIL'} {r['test_name']}")
    return summary


# ============ CLI INTERFACE ============

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="QtTune Agent Tribunal — Multi-agent code review orchestration")
    parser.add_argument("--golden", action="store_true",
                        help="Run golden test suite (reviewer unit test)")
    parser.add_argument("--proposal", type=str, required=False,
                        help="Proposal text for debate")
    parser.add_argument("--diff", type=str, required=False,
                        help="Path to code diff file")
    parser.add_argument("--context", type=str, required=False,
                        help="Path to surrounding code context file")
    parser.add_argument("--header", action="store_true",
                        help="Review target is header-only (C ABI stub)")

    args = parser.parse_args()

    if args.golden:
        run_golden_tests()
    elif args.proposal:
        if args.diff and not os.path.exists(args.diff):
            raise SystemExit(f"ERROR: --diff path not found: {args.diff}\n"
                            "Provide a valid diff file path.")
        if args.context and not os.path.exists(args.context):
            raise SystemExit(f"ERROR: --context path not found: {args.context}\n"
                            "Provide a valid context file path.")
        code_diff = open(args.diff).read() if args.diff else ""
        code_context = open(args.context).read() if args.context else ""
        result = run_debate(args.proposal, code_diff, code_context,
                            header_artifact=args.header)
        print(json.dumps(result, indent=2))
    else:
        print(__doc__)
        