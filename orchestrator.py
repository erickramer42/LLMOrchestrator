#!/usr/bin/env python3
"""QtTune Agent Tribunal — CLI entrypoint.

Debates live in debate.py, agent calls in agent_client.py, judging and
guardrails in adjudication.py, configuration in config.py, golden tests
in golden_tests.py. This file only parses arguments and dispatches.

Usage:
    python orchestrator.py --golden
    python orchestrator.py --proposal "..." [--diff file] [--context file] [--header]
    python orchestrator.py --index <repo-path> [--no-llm]

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

def run_index(target: str, use_llm: bool) -> None:
    """Build and save the repo context pack. Imported lazily so debate
    and golden runs never depend on the indexer module."""
    from repo_context import build_index, save_index

    index = build_index(target, use_llm=use_llm)
    out_path = save_index(index)
    print(f"Wrote {out_path}: {len(index['files'])} files, "
          f"{len(index['types'])} types, "
          f"{len(index['constants'])} constants")

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
    parser.add_argument("--index", type=str, required=False, metavar="REPO_PATH",
                        help="Build repo_context.json context pack for REPO_PATH")
    parser.add_argument("--no-llm", action="store_true",
                        help="Index deterministically, skipping LLM purpose "
                             "summaries (applies to --index)")

    args = parser.parse_args()

    if args.index:
        if args.golden or args.proposal:
            raise SystemExit(
                "ERROR: --index cannot be combined with --golden or --proposal.\n"
                "Run the index build as a separate invocation.")
        run_index(args.index, use_llm=not args.no_llm)
    elif args.golden:
        run_golden_tests()
    elif args.proposal:
        if args.diff and not os.path.exists(args.diff):
            raise SystemExit(f"ERROR: --diff path not found: {args.diff}\n"
                             "Provide a valid diff file path.")
        if args.context and not os.path.exists(args.context):
            raise SystemExit(f"ERROR: --context path not found: {args.context}\n"
                             "Provide a valid file context file path.")
        code_diff = open(args.diff).read() if args.diff else ""
        code_context = open(args.context).read() if args.context else ""
        result = run_debate(args.proposal, code_diff, code_context,
                            header_artifact=args.header)
        print(json.dumps(result, indent=2))
    else:
        print(__doc__)
        