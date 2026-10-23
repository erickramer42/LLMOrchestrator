#!/usr/bin/env python3
"""bakeoff.py — reviewer slot bake-off. One model at a time, isolated calls."""

import time, argparse

from eval_harness.raw_call import review
from review_fixtures import ABI_TYPE_LEAK, CANFD_BUFFER_OVERFLOW, CLEAN_ABI_HEADER
from reviewer_prompt import (REVIEWER_SYSTEM, HEADER_SCOPE_CLAUSE,
                             IMPL_SCOPE_CLAUSE, PROMPT_VERSION)

CASES = [
    # (name, expect_bug, code, is_header)
    ("canfd_buffer_overflow", True, CANFD_BUFFER_OVERFLOW, False),

    ("abi_type_leak", True, ABI_TYPE_LEAK, True),

    ("unchecked_thread_share", True,
     '// core/src/rx_queue.cpp\n'
     'static Frame rx_ring[256];\n'
     'static int head = 0, tail = 0;\n'
     'void on_rx(Frame f) { head = (head + 1) % 256; rx_ring[head] = f; }\n'
     'Frame* peek(void) { return &rx_ring[tail]; }', False),

    ("qt_in_core", True,
     '// core/src/logsink.cpp\n'
     '#include <QString>\n'
     '#include <QDebug>\n'
     'void log_frame(const Frame* f) { qDebug() << f->channel_id; }', False),

    ("exception_over_abi", True,
     '// core/src/config.cpp\n'
     'extern "C" int qttune_load_config(const char* path) {\n'
     '    auto doc = parse_json_or_throw(path);\n'
     '    return doc.size();\n'
     '}', False),

    ("clean_pattern", False, CLEAN_ABI_HEADER, True),
]

def call(model: str, code: str, is_header: bool):
    """Returns (reply, failure). failure is None on success, else
    'timeout' or 'parse' (no attempt yielded a JSON object)."""
    system = REVIEWER_SYSTEM + (HEADER_SCOPE_CLAUSE if is_header
                                else IMPL_SCOPE_CLAUSE)
    out, failure, _ = review(model, system, code)
    return out, failure


def tally(outcomes) -> dict:
    """Score (expect_bug, failure, flagged) triples.

    Clean passes are tallied SEPARATELY from bug hits — conflating them
    made 'Detection' read N+1/N+1 and 'Clean' go negative on any miss.
    An unusable reply on a bug case is a miss (fn), not a dropped case.
    Invariants (third occurrence of this bug class; keep them):
        tp + fn == number of expect_bug cases
        fp + clean_ok + clean_failed == number of clean cases
    """
    score = {"tp": 0, "fn": 0, "fp": 0, "clean_ok": 0, "clean_failed": 0,
             "json_fails": 0, "timeouts": 0, "bug_total": 0, "clean_total": 0}
    for expect_bug, failure, flagged in outcomes:
        score["bug_total" if expect_bug else "clean_total"] += 1
        if failure:
            score["timeouts" if failure == "timeout" else "json_fails"] += 1
        if expect_bug:
            score["tp" if (flagged and not failure) else "fn"] += 1
        elif failure:
            score["clean_failed"] += 1
        else:
            score["fp" if flagged else "clean_ok"] += 1
    return score


def run(model: str):
    print(f"\n{'='*60}\nMODEL: {model} | Prompt: {PROMPT_VERSION}\n{'='*60}")
    outcomes, times = [], []
    for name, expect_bug, code, is_header in CASES:
        t0 = time.time()
        out, failure = call(model, code, is_header)
        times.append(time.time() - t0)
        flagged = bool(out.get("blockers"))
        outcomes.append((expect_bug, failure, flagged))
        if failure:
            print(f"  ✗✗ {name}: {'TIMEOUT' if failure == 'timeout' else 'JSON PARSE FAILURE'}"
                  f"{' (counted as MISS)' if expect_bug else ''}")
        elif expect_bug:
            print(f"  {'✓ HIT ' if flagged else '✗ MISS'} {name}"
                  f" — {out.get('blockers', ['(none)'])[:1]}")
        else:
            print(f"  {'✗ FP  ' if flagged else '✓ OK  '} {name} (clean)")
    score = tally(outcomes)
    avg = sum(times) / len(times) if times else 0
    print(f"\n  Detection: {score['tp']}/{score['bug_total']} bugs | "
          f"False pos: {score['fp']}/{score['clean_total']} | "
          f"Clean: {score['clean_ok']}/{score['clean_total']} | "
          f"JSON fails: {score['json_fails']} | Timeouts: {score['timeouts']} | "
          f"Avg latency: {avg:.1f}s")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Model bake-off for reviewer slot")
    parser.add_argument("models", nargs="+", metavar="MODEL",
                        help="Models to compare (e.g. laguna-xs-2.1 gemma4:12b)")
    args = parser.parse_args()

    for m in args.models:
        run(m)
        