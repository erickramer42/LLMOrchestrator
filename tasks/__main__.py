"""The task board's command line. Output is JSON on stdout. Exit status: 0
done, 1 refused or failed, 2 usage error.

    python -m tasks submit --project havne --kind second_read --commit <sha> \\
        --findings findings.json [--question "..."]
    python -m tasks list [--state open] [--limit 20]
    python -m tasks get <task_id> [--wait 600] [--caller-tokens N]
    python -m tasks claim <task_id> [--worker name]
    python -m tasks submit-result <task_id> items.json [--worker name]

findings.json is a list of {claim, file, quote?, line?}; items.json is the
worker's list of {finding, verdict, file, quote, reason}. LLMORCH_RECORDS_DIR
and LLMORCH_PROJECTS_FILE override where tasks and projects.json are read.
"""

import argparse
import json
import sys
from pathlib import Path

from tasks.board import Board, TaskError
from tasks.kinds import SECOND_READ


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tasks",
                                     description="Post work for another agent and read "
                                                 "its checked answer.")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("submit", help="Post a task")
    s.add_argument("--project", required=True)
    s.add_argument("--kind", default=SECOND_READ)
    s.add_argument("--commit", required=True, help="the work branch's commit")
    s.add_argument("--findings", required=True, help="a JSON file: the findings")
    s.add_argument("--question", default="")
    s.add_argument("--caller", default="cli")
    ls = sub.add_parser("list", help="List tasks, newest first")
    ls.add_argument("--state")
    ls.add_argument("--limit", type=int, default=20)
    g = sub.add_parser("get", help="A task's state and, once done, its checked result")
    g.add_argument("task_id")
    g.add_argument("--wait", type=float, default=0, help="seconds to wait for it to finish")
    g.add_argument("--caller-tokens", type=int, help="tokens this session spent on the task")
    c = sub.add_parser("claim", help="Claim a task as its worker")
    c.add_argument("task_id")
    c.add_argument("--worker", default="cli")
    r = sub.add_parser("submit-result", help="Send a claimed task's answer")
    r.add_argument("task_id")
    r.add_argument("items", help="a JSON file: the answer's items")
    r.add_argument("--worker", default="cli")
    args = parser.parse_args(argv)

    board = Board()
    try:
        if args.command == "submit":
            out = board.submit(args.kind, args.project, args.commit,
                               {"findings": _load(args.findings), "question": args.question},
                               caller=args.caller)
        elif args.command == "list":
            out = {"tasks": board.list(args.state, max(1, args.limit))}
        elif args.command == "get":
            if args.wait:
                board.wait(args.task_id, args.wait)
            out = board.get(args.task_id, args.caller_tokens)
        elif args.command == "claim":
            out = board.claim(args.task_id, args.worker)
        else:
            out = board.submit_result(args.task_id, args.worker, _load(args.items))
    except (TaskError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if out.get("state") == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
