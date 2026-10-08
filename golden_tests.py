"""Golden test suite — reviewer unit tests via live model, plus
deterministic guardrail regression tests (no LLM)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from adjudication import demote_hedged_blockers
from agent_client import call_agent
from config import (MODELS, REVIEWER_HEADER_PROMPT, REVIEWER_IMPL_PROMPT,
                    TEMPERATURE_RETRY)


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
        demoted_out = demote_hedged_blockers(fake_out, "questions")
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
    TEST_CASES = [
        {
            "name": "buffer_overflow_can_fd",
            "snippet": ('// core/src/frame_decode.cpp\n'
                        'void decode(const PASSTHRU_MSG* msg) {\n'
                        '    uint8_t buf[8];\n'
                        '    memcpy(buf, msg->DataSize);\n'
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

    results = run_hedge_unit_tests()
    for tc in TEST_CASES:
        prompt = (REVIEWER_HEADER_PROMPT if tc.get("header", False)
                 else REVIEWER_IMPL_PROMPT)
        out = call_agent(MODELS["code_reviewer"], prompt, tc["snippet"],
                         TEMPERATURE_RETRY)
        out = demote_hedged_blockers(out, "questions")

        detected = bool(out.get("blockers"))
        if tc.get("expected_to_block", False):
            passed = detected
        else:
            passed = not detected

        results.append({"test_name": tc["name"],
                        "expected_blocked": tc.get("expected_to_block", False),
                        "detected": detected,
                        "test_passed": passed})

    summary = {"total_tests": len(results),
               "passed": sum(r["test_passed"] for r in results),
               "failed": len(results) - sum(r["test_passed"] for r in results),
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
