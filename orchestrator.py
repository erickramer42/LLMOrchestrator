#!/usr/bin/env python3
"""QtTune Agent Tribunal — CLI entrypoint.

Debates live in debate.py, agent calls in agent_client.py, judging and
guardrails in adjudication.py, configuration in config.py, golden tests
in golden_tests.py. This file only parses arguments and dispatches.

Usage:
    python orchestrator.py --golden
    python orchestrator.py --proposal "..." [--diff file] [--context file] [--header]
                           [--index-file path]
    python orchestrator.py --index <repo-path> [--no-llm] [--index-out path]

Exit status, so a CI job or a hook can gate on a review:
    0  approved, with or without open questions
    1  blockers still stand after the last round; --golden: a test failed
    2  usage error (argparse's own)
    3  no decision: an agent failed or the input was refused, so a person
       must review it
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from adjudication import (APPROVED_FOR_MERGE, APPROVED_WITH_OPEN_QUESTIONS,
                          MAX_ROUNDS_VERDICT)
from debate import run_debate
from golden_tests import print_summary, run_golden_tests

EXIT_APPROVED = 0
EXIT_BLOCKED = 1
EXIT_NO_DECISION = 3


def exit_status(final_verdict: str) -> int:
    """The exit status of a review with this final verdict. Anything but
    an approval or blockers at the round limit is no decision, including
    a verdict this function does not know (fail closed)."""
    if final_verdict in (APPROVED_FOR_MERGE, APPROVED_WITH_OPEN_QUESTIONS):
        return EXIT_APPROVED
    if final_verdict == MAX_ROUNDS_VERDICT:
        return EXIT_BLOCKED
    return EXIT_NO_DECISION


def run_index(target: str, use_llm: bool, out_path: str = None) -> None:
    """Build and save the repo context pack, to out_path or the default
    repo_context.json. Imported here, so a debate never loads the indexer
    or its summary prompt."""
    from indexer import build_index, save_index

    index = build_index(target, use_llm=use_llm)
    out_path = save_index(index, out_path)
    print(f"Wrote {out_path}: {len(index['files'])} files, "
          f"{len(index['types'])} types, "
          f"{len(index['constants'])} constants")


def read_input(path: str) -> str:
    # Explicit UTF-8: the Windows default (cp1252) silently garbles
    # non-ASCII characters in diffs before the models see them.
    return Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the command line, run the chosen mode and return the exit
    status (see the module docstring)."""
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
    parser.add_argument("--index-out", type=str, required=False, metavar="PATH",
                        help="Write the index to PATH instead of "
                             "repo_context.json (with --index)")
    parser.add_argument("--index-file", type=str, required=False, metavar="PATH",
                        help="Retrieve from the index at PATH instead of "
                             "repo_context.json (with --proposal)")

    args = parser.parse_args(argv)

    if not args.proposal and (args.diff or args.context or args.header):
        parser.error("--diff, --context and --header require --proposal")
    if args.proposal and not (args.diff or args.context):
        parser.error("--proposal needs --diff or --context: there is no code "
                     "to review")
    if args.no_llm and not args.index:
        parser.error("--no-llm applies only to --index")
    if args.index_out and not args.index:
        parser.error("--index-out applies only to --index")
    if args.index_file and not args.proposal:
        parser.error("--index-file applies only to --proposal")
    for flag, path in (("--diff", args.diff), ("--context", args.context)):
        if path and not Path(path).is_file():
            parser.error(f"{flag} path not found: {path}")

    if args.index:
        run_index(args.index, use_llm=not args.no_llm, out_path=args.index_out)
        return 0
    if args.golden:
        summary = run_golden_tests()
        print_summary(summary)
        return 1 if summary["failed"] else 0
    if args.proposal:
        code_diff = read_input(args.diff) if args.diff else ""
        code_context = read_input(args.context) if args.context else ""
        result = run_debate(args.proposal, code_diff, code_context,
                            header_artifact=args.header,
                            index_path=args.index_file)
        print(json.dumps(result, indent=2))
        return exit_status(result["final_verdict"])
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
