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
from pathlib import Path

# Re-exports: keeps older scripts / one-liners importing from
# orchestrator working during the transition.
from adjudication import derive_verdict, demote_hedged_blockers  # noqa: F401
from agent_client import call_agent  # noqa: F401
from config import MODELS  # noqa: F401
from debate import run_debate
from golden_tests import run_golden_tests

def run_index(target: str, use_llm: bool) -> None:
    """Build and save the repo context pack. debate.py imports
    repo_context for retrieval anyway; the lazy import only keeps the
    indexer entry points out of this module's namespace."""
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--golden", action="store_true",
                      help="Run golden test suite (reviewer unit test)")
    mode.add_argument("--proposal", type=str, required=False,
                      help="Proposal text for debate")
    mode.add_argument("--index", type=str, required=False, metavar="REPO_PATH",
                      help="Build repo_context.json context pack for REPO_PATH")
    parser.add_argument("--diff", type=str, required=False,
                        help="Path to code diff file (with --proposal)")
    parser.add_argument("--context", type=str, required=False,
                        help="Path to surrounding code context file "
                             "(with --proposal)")
    parser.add_argument("--header", action="store_true",
                        help="Review target is header-only (C ABI stub)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Index deterministically, skipping LLM purpose "
                             "summaries (applies to --index)")

    args = parser.parse_args()

    if not args.proposal and (args.diff or args.context or args.header):
        parser.error("--diff, --context and --header require --proposal")
    if args.no_llm and not args.index:
        parser.error("--no-llm applies only to --index")

    def read_input(path: str) -> str:
        # Explicit UTF-8: the Windows default (cp1252) silently garbles
        # non-ASCII characters in diffs before the models see them.
        return Path(path).read_text(encoding="utf-8", errors="replace")

    if args.index:
        run_index(args.index, use_llm=not args.no_llm)
    elif args.golden:
        run_golden_tests()
    elif args.proposal:
        if args.diff and not os.path.exists(args.diff):
            raise SystemExit(f"ERROR: --diff path not found: {args.diff}\n"
                             "Provide a valid diff file path.")
        if args.context and not os.path.exists(args.context):
            raise SystemExit(f"ERROR: --context path not found: {args.context}\n"
                             "Provide a valid context file path.")
        code_diff = read_input(args.diff) if args.diff else ""
        code_context = read_input(args.context) if args.context else ""
        result = run_debate(args.proposal, code_diff, code_context,
                            header_artifact=args.header)
        print(json.dumps(result, indent=2))
    else:
        print(__doc__)
        