"""Golden test suite — reviewer unit tests via live model, plus
deterministic guardrail regression tests (no LLM).

Each model fixture is reviewed as a debate's round-1 reviewer reviews it
(debate.review_round1): the fenced transcript, the layer note, then the
evidence check and hedge demotion. Only the first attempt's temperature
differs (GOLDEN_TEMPERATURE)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from adjudication import JUDGE_VERSION, demote_hedged_blockers
from config import MODELS, TEMPERATURE_RETRY
from debate import review_round1
from review_fixtures import ABI_TYPE_LEAK, CANFD_BUFFER_OVERFLOW, CLEAN_ABI_HEADER
from reviewer_prompt import PROMPT_VERSION

# Each fixture's proposal. Neutral on purpose: a fixture name such as
# "buffer_overflow_can_fd" would tell the reviewer what to find.
GOLDEN_PROPOSAL = "Review the code in the CODE CONTEXT."
# 0.05 keeps the suite a repeatable reviewer unit test, though a debate's
# round 1 samples at 0.7 (ADR-0002, "Golden Suite Routing").
GOLDEN_TEMPERATURE = TEMPERATURE_RETRY


def score_fixture(out: dict, expected_to_block: bool) -> dict:
    """Pass/fail for one live-model fixture. An unusable reply (parse,
    schema or transport failure) FAILS regardless of expectation; it
    must never count as a clean pass."""
    failed = out.get("verdict") == "PARSE_FAILURE"
    detected = bool(out.get("blockers"))
    passed = (not failed) and (detected == expected_to_block)
    result = {"expected_blocked": expected_to_block, "detected": detected,
              "agent_failure": failed, "test_passed": passed}
    if failed:
        result["failure_reason"] = out.get("failure_reason", "unknown")
    return result


def run_hedge_unit_tests() -> List[dict]:
    """Deterministic guardrail regression tests — no LLM involved.

    Blocker texts are taken verbatim from the 2026-10-07 bridge-refactor
    debate (decision_debate_20261007_203917) plus synthetic controls.
    Pins demote_hedged_blockers() behavior so regex changes can't
    silently regress it.
    """
    CASES = [
        # --- real production texts that SHOULD demote ---
        ("Memory safety violation - the lambda captures a copy of the "
         "struct while frame->data may reference freed stack memory in "
         "the worker thread", True),
        ("Comment states 'stack-owned by mock_worker' but the pointer "
         "might be invalid when executed on the GUI thread", True),
        ("m_currentFrameCount could have a race condition between the "
         "worker thread and the GUI thread", True),
        # --- real production texts that should NOT demote (assertions) ---
        ("qttune_decode_signal() called with hardcoded 8-byte buffer size "
         "in handleFrameInternal() line 168 while CAN-FD frames can be "
         "64+ bytes", False),
        ("qttunebridge.h line 4 includes QAbstractListModel and "
         "QSortFilterProxyModel - the core module must not include Qt "
         "headers", False),
        # --- synthetic controls ---
        ("This appears to be a potential buffer overrun in the decode "
         "path", True),
        ("memcpy writes msg->DataSize bytes into an 8-byte stack buffer "
         "with no bounds check at line 4", False),
    ]
    results = []
    for i, (text, should_demote) in enumerate(CASES, 1):
        fake_out = {"verdict": "reject", "blockers": [text],
                    "questions": [], "nits": []}
        demoted_out, _ = demote_hedged_blockers(fake_out, "questions")
        was_demoted = len(demoted_out.get("blockers", [])) == 0
        results.append({
            "test_name": f"hedge_unit_{i}",
            "text": text,
            "should_demote": should_demote,
            "was_demoted": was_demoted,
            "test_passed": was_demoted == should_demote,
        })
    return results


def run_golden_tests() -> dict:
    """Run the hedge units and the live-model fixtures, write the summary
    to gold_tests/run_<utc>.json and return it. A fixture's snippet is its
    CODE CONTEXT, so the reviewer may quote it under any file name."""
    TEST_CASES = [
        {
            "name": "buffer_overflow_can_fd",
            "snippet": CANFD_BUFFER_OVERFLOW,
            "expected_to_block": True,
            "header": False,
        },
        {
            "name": "abi_type_leak",
            "snippet": ABI_TYPE_LEAK,
            "expected_to_block": True,
            "header": True,
        },
        {
            "name": "clean_abi_pattern",
            "snippet": CLEAN_ABI_HEADER,
            "expected_to_block": False,
            "header": True,
        },
    ]

    results = run_hedge_unit_tests()
    for tc in TEST_CASES:
        entry = review_round1(GOLDEN_PROPOSAL, code_context=tc["snippet"],
                              header_artifact=tc.get("header", False),
                              temperature=GOLDEN_TEMPERATURE)
        results.append({
            "test_name": tc["name"],
            **score_fixture(entry["reviewer"], tc.get("expected_to_block", False)),
            "evidence_demoted": entry["evidence_demotions"]["reviewer_demoted"],
            "hedge_demoted": entry["hedge_demotions"]["reviewer_demoted"],
            "attempts": len(entry["telemetry"]["reviewer"]),
        })

    passed = sum(r["test_passed"] for r in results)
    summary = {"metadata": {"prompt_version": PROMPT_VERSION,
                            "judge_version": JUDGE_VERSION,
                            "model": MODELS["code_reviewer"],
                            "temperature": GOLDEN_TEMPERATURE,
                            "proposal": GOLDEN_PROPOSAL},
               "total_tests": len(results),
               "passed": passed,
               "failed": len(results) - passed,
               "individual_results": results}

    test_log = Path("gold_tests") / f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    test_log.parent.mkdir(exist_ok=True)
    test_log.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def print_summary(summary: dict) -> None:
    """The CLI's report of a run_golden_tests() summary."""
    print(f"\n{'='*50}")
    print(f"Golden Tests: {summary['passed']}/{summary['total_tests']} passed")
    print(f"{'='*50}")
    for r in summary["individual_results"]:
        note = (f"  (agent failure: {r['failure_reason']})"
                if r.get("agent_failure") else "")
        if r.get("evidence_demoted"):
            note += f"  ({r['evidence_demoted']} blocker(s) evidence-demoted)"
        print(f"  {'PASS' if r['test_passed'] else 'FAIL'} {r['test_name']}{note}")
