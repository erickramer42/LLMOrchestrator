#!/usr/bin/env python3
"""bakeoff.py — reviewer slot bake-off. One model at a time, isolated calls."""

import json, sys, time, requests, argparse
from pathlib import Path

from reviewer_prompt import (REVIEWER_SYSTEM, HEADER_SCOPE_CLAUSE,
                             IMPL_SCOPE_CLAUSE, PROMPT_VERSION)

OLLAMA = "http://localhost:11434/api/chat"

CASES = [
    # (name, expect_bug, code, is_header)
    ("canfd_buffer_overflow", True,
     '// core/src/frame_decode.cpp\n'
     'void decode(const PASSTHRU_MSG* msg) {\n'
     '    uint8_t buf[8];\n'
     '    memcpy(buf, msg->Data, msg->DataSize);\n'
     '}', False),

    ("abi_type_leak", True,
     '// core/include/qttune/session.h  (public C ABI header)\n'
     '#include <vector>\n'
     '#include <string>\n'
     'extern "C" std::vector<std::string> qttune_get_session_names(qttune_session_t* s);',
     True),

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

    ("clean_pattern", False,
     '// core/include/qttune/init.h\n'
     '#pragma once\n'
     '#ifdef __cplusplus\nextern "C" {\n#endif\n'
     'typedef struct qttune_ctx qttune_ctx;\n'
     'int qttune_init(qttune_ctx** out);\n'
     'int qttune_shutdown(qttune_ctx* ctx);\n'
     '#ifdef __cplusplus\n}\n#endif', True),
]

def call(model: str, code: str, is_header: bool):
    system = REVIEWER_SYSTEM + (HEADER_SCOPE_CLAUSE if is_header
                                else IMPL_SCOPE_CLAUSE)
    for attempt in range(3):
        payload = {"model": model, "stream": False, "format": "json",
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": code}],
                   "options": {"temperature": 0.2 if attempt == 0 else 0.05,
                               "num_ctx": 16384}}
        try:
            r = requests.post(OLLAMA, json=payload, timeout=600).json()
            result = json.loads(r["message"]["content"]), True
            return result
        except json.JSONDecodeError:
            pass
    return {}, False

def run(model: str):
    print(f"\n{'='*60}\nMODEL: {model} | Prompt: {PROMPT_VERSION}\n{'='*60}")
    score = {"tp": 0, "fn": 0, "fp": 0, "json_fails": 0, "times": []}
    for name, expect_bug, code, is_header in CASES:
        t0 = time.time()
        out, ok = call(model, code, is_header)
        elapsed = time.time() - t0
        score["times"].append(elapsed)
        if not ok:
            score["json_fails"] += 1
            print(f"  ✗✗ {name}: JSON PARSE FAILURE")
            continue
        flagged = bool(out.get("blockers"))
        if expect_bug:
            hit = flagged
            score["tp" if hit else "fn"] += 1
            print(f"  {'✓ HIT ' if hit else '✗ MISS'} {name}"
                  f" — {out.get('blockers', ['(none)'])[:1]}")
        else:
            score["fp" if flagged else "tp"] += 1
            print(f"  {'✗ FP  ' if flagged else '✓ OK  '} {name} (clean)")
    avg = sum(score["times"]) / len(score["times"]) if score["times"] else 0
    bug_total = score["tp"] + score["fn"] 
    clean_passes = score["tp"] - bug_total 
    print(f"\n  Detection: {score['tp']}/{bug_total} bugs | False pos: {score['fp']}/1 | "
          f"Clean: {clean_passes}/1 | JSON fails: {score['json_fails']} | Avg latency: {avg:.1f}s")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Model bake-off for reviewer slot")
    parser.add_argument("models", nargs="+", metavar="MODEL",
                        help="Models to compare (e.g. laguna-xs-2.1 gemma4:12b)")
    args = parser.parse_args()
    
    for m in args.models:
        run(m)
        