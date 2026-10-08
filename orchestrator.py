#!/usr/bin/env python3
"""QtTune Agent Tribunal — CLI entrypoint.

Debates live in debate.py, agent calls in agent_client.py, judging and
guardrails in adjudication.py, configuration in config.py, golden tests
in golden_tests.py. This file only parses arguments and dispatches.

Usage:
    python orchestrator.py --golden
    python orchestrator.py --proposal "..." [--diff file] [--context file] [--header]

Author: Eric | License: MIT
"""

import json
import os

# Re-exports: keeps older scripts / one-liners importing from
# orchestrator working during the transition.
from adjudication import derive_verdict, demote_hedged_blockers  # noqa: F401
from agent_client import call_agent  # noqa: F401
from config import MODELS  # noqa: F401
from debate import run_debate
from golden_tests import run_golden_tests

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
        