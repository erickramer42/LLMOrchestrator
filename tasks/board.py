"""The task board: one JSON record per task under <records>/tasks/, shared
by every process that names the same directory (the CLI, the MCP server).

A task is open until a worker claims it, then claimed until its answer is
checked: done, or failed. Every change to a record holds the task's lock
file, created exclusively, so two workers never both claim a task. A
worker's quotes are checked against the files at the task's commit (or,
for git-ignored files, the working tree as hashed at the claim) by
adjudication.judge_finding; an item that fails goes back once with the
reason, then is reported as unverified. Nothing here calls a model.
"""

import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import adjudication
from tasks import kinds
from tasks.projects import Project, ProjectError, load_project

BOARD_VERSION = "b1"
OPEN, CLAIMED, DONE, FAILED = "open", "claimed", "done", "failed"
TASK_ID = re.compile(r"task_\d{8}_\d{6}_[0-9a-f]{6}")
MAX_ATTEMPTS = 2   # the answer, then one retry of its rejected items
LOCK_WAIT_S = 5.0
LOCK_STALE_S = 30.0


class TaskError(ValueError):
    """A request the board refuses; the message says why."""


def records_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    return Path(os.environ.get("LLMORCH_RECORDS_DIR") or root / "mcp_records")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chars(value) -> int:
    return len(json.dumps(value, ensure_ascii=False))


class Board:
    def __init__(self, directory: Optional[Path] = None,
                 projects_file: Optional[Path] = None):
        self.dir = Path(directory or records_dir() / "tasks")
        self.projects_file = projects_file

    # Storage

    def _path(self, task_id: str) -> Path:
        if not TASK_ID.fullmatch(task_id or ""):
            raise TaskError(f"not a task id: {task_id!r}")
        return self.dir / f"{task_id}.json"

    def _read(self, task_id: str) -> dict:
        path = self._path(task_id)
        if not path.is_file():
            raise TaskError(f"no task {task_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, task: dict) -> None:
        path = self._path(task["task_id"])
        tmp = path.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _locked(self, task_id: str):
        board = self

        class Lock:
            def __enter__(self):
                board._read(task_id)  # no task, no lock file
                lock = board._path(task_id).with_suffix(".lock")
                deadline = time.monotonic() + LOCK_WAIT_S
                while True:
                    try:
                        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                        self.lock = lock
                        return board._read(task_id)
                    except FileExistsError:
                        try:
                            if time.time() - lock.stat().st_mtime > LOCK_STALE_S:
                                lock.unlink()
                                continue
                        except FileNotFoundError:
                            continue
                        if time.monotonic() > deadline:
                            raise TaskError(f"task {task_id} is busy; try again") from None
                        time.sleep(0.05)

            def __exit__(self, *exc):
                self.lock.unlink(missing_ok=True)
        return Lock()

    def _project(self, name: str) -> Project:
        return load_project(name, self.projects_file)

    # Submitters

    def submit(self, kind: str, project: str, commit: str, payload, caller: str = "cli") -> dict:
        if kind not in kinds.KINDS:
            raise TaskError(f"no task kind {kind!r}; kinds: {', '.join(kinds.KINDS)}")
        try:
            spec = kinds.KINDS[kind]
            payload = spec["payload"](payload)
            proj = self._project(project)
            full = proj.resolve(commit)
            cited = [proj.check_path(p) for p in spec["cited"](payload)]
            files = list(dict.fromkeys(cited + list(proj.always) + proj.matching_rules(cited)))
            _deny(proj, payload, "the task")
        except (kinds.PayloadError, ProjectError) as exc:
            raise TaskError(str(exc)) from None
        task_id = f"task_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{secrets.token_hex(3)}"
        task = {"task_id": task_id, "kind": kind, "kind_version": kinds.KINDS[kind]["version"],
                "board_version": BOARD_VERSION, "judge_version": adjudication.JUDGE_VERSION,
                "project": project, "commit": full, "state": OPEN, "created_utc": _now(),
                "caller": caller, "payload": payload, "files": files, "claim": None,
                "attempts": [], "result": None, "failure": None,
                "cost": {"submit_chars": _chars(payload), "result_chars": 0,
                         "caller_tokens": None, "claim_chars": 0, "worker_chars": 0}}
        self.dir.mkdir(parents=True, exist_ok=True)
        self._write(task)
        return {"task_id": task_id, "state": OPEN, "files": files}

    def get(self, task_id: str, caller_tokens: Optional[int] = None) -> dict:
        with self._locked(task_id) as task:
            view = _view(task)
            task["cost"]["result_chars"] += _chars(view)
            if caller_tokens is not None:
                task["cost"]["caller_tokens"] = int(caller_tokens)
            self._write(task)
        return view

    def wait(self, task_id: str, seconds: float) -> None:
        """Returns once the task is done or failed, or the time is up."""
        deadline = time.monotonic() + max(0.0, seconds)
        while (self._read(task_id)["state"] not in (DONE, FAILED)
               and time.monotonic() < deadline):
            time.sleep(1.0)

    def list(self, state: Optional[str] = None, limit: int = 20) -> List[dict]:
        rows = []
        for path in sorted(self.dir.glob("task_*.json"), reverse=True) if self.dir.is_dir() else []:
            task = json.loads(path.read_text(encoding="utf-8"))
            if state and task["state"] != state:
                continue
            rows.append({"task_id": task["task_id"], "kind": task["kind"],
                         "project": task["project"], "commit": task["commit"][:12],
                         "state": task["state"], "created_utc": task["created_utc"],
                         "findings": len(task["payload"]["findings"])})
            if len(rows) >= limit:
                break
        return rows

    # Workers

    def claim(self, task_id: str, worker: str) -> dict:
        with self._locked(task_id) as task:
            if task["state"] in (DONE, FAILED):
                raise TaskError(f"task {task_id} is {task['state']}")
            if task["state"] == CLAIMED and task["claim"]["worker"] != worker:
                raise TaskError(f"task {task_id} is claimed by another worker")
            if task["state"] == OPEN:
                task["claim"] = self._claim(task, worker)
                task["state"] = CLAIMED
            bundle = _bundle(task)
            task["cost"]["claim_chars"] += _chars(bundle)
            self._write(task)
        return bundle

    def _claim(self, task: dict, worker: str) -> dict:
        try:
            proj = self._project(task["project"])
            checkout = proj.checkout(task["commit"])
            tracked = [p for p in task["files"] if proj.tracked(task["commit"], p)]
            dirty = proj.dirty(checkout, tracked)
            if dirty:
                raise TaskError(f"the checkout has changes to {', '.join(dirty)}; "
                                "commit them, or post the task at a commit that has them")
            files, hashes, missing = [], {}, []
            for path in task["files"]:
                if path in tracked:
                    files.append({"path": path, "read_from": str(checkout / path)})
                elif (proj.root / path).is_file():
                    hashes[path] = proj.read_working(path)[1]
                    files.append({"path": path, "read_from": str(proj.root / path)})
                else:
                    missing.append(path)
        except ProjectError as exc:
            raise TaskError(str(exc)) from None
        return {"worker": worker, "claimed_utc": _now(), "checkout": str(checkout),
                "files": files, "working_hashes": hashes, "missing": missing}

    def submit_result(self, task_id: str, worker: str, items) -> dict:
        with self._locked(task_id) as task:
            if task["state"] != CLAIMED or task["claim"]["worker"] != worker:
                raise TaskError(f"task {task_id} is not claimed by this worker")
            task["cost"]["worker_chars"] += _chars(items)
            outcomes = self._check(task, items)
            task["attempts"].append({"submitted_utc": _now(), "items": items,
                                     "outcomes": outcomes})
            rejected = [o for o in outcomes if o["outcome"] == "rejected"]
            if rejected and len(task["attempts"]) < MAX_ATTEMPTS:
                self._write(task)
                return {"task_id": task_id, "state": CLAIMED, "status": "retry",
                        "rejected": [{k: o[k] for k in ("finding", "why")} for o in rejected],
                        "instructions": "Fix or drop each rejected item and call submit_result "
                                        "again with those items only; items that passed stand."}
            self._finish(task)
            self._write(task)
            return _view(task)

    def _check(self, task: dict, items) -> List[dict]:
        if not isinstance(items, list) or not items:
            return [{"finding": None, "outcome": "rejected",
                     "why": "the answer must be a non-empty list of items"}]
        n = len(task["payload"]["findings"])
        settled = {o["finding"] for a in task["attempts"] for o in a["outcomes"]
                   if o["outcome"] == "passed"}
        sources = _Sources(self, task)
        out, seen = [], set()
        for raw in items:
            item, why = kinds.KINDS[task["kind"]]["item"](raw, n)
            finding = item["finding"] if item else (raw.get("finding") if isinstance(raw, dict)
                                                     else None)
            if why is None and (finding in seen or finding in settled):
                why = f"finding {finding} already has an item"
            if why is None and item["verdict"] in kinds.CHECKED:
                why = sources.check(item)
            if item:
                seen.add(finding)
            out.append({"finding": finding, "outcome": "rejected" if why else "passed",
                        "why": why, "item": item})
        return out

    def _finish(self, task: dict) -> None:
        passed, last = {}, {}
        for attempt in task["attempts"]:
            for o in attempt["outcomes"]:
                if o["outcome"] == "passed":
                    passed.setdefault(o["finding"], o["item"])
                elif isinstance(o["finding"], int):
                    last[o["finding"]] = o["why"]
        answered = set(passed) | set(last)
        result = {"supported": [], "refuted": [], "unclear": [],
                  "unverified": [{"finding": f, "why": why} for f, why in sorted(last.items())
                                 if f not in passed],
                  "unanswered": [i for i in range(len(task["payload"]["findings"]))
                                 if i not in answered]}
        for f in sorted(passed):
            result[passed[f]["verdict"]].append(passed[f])
        task["result"] = result
        task["state"] = DONE
        if not passed and not last:
            task["state"], task["failure"] = FAILED, "no item had the answer's shape"
        try:
            _deny(self._project(task["project"]), result, "the result")
        except (ProjectError, TaskError) as exc:
            task["state"], task["result"], task["failure"] = FAILED, None, str(exc)


class _Sources:
    """The task's files as quote sources, read once per check."""

    def __init__(self, board: Board, task: dict):
        self.board, self.task = board, task
        self.cache: Dict[str, Optional[str]] = {}

    def _text(self, path: str) -> Optional[str]:
        if path not in self.cache:
            proj = self.board._project(self.task["project"])
            hashes = self.task["claim"]["working_hashes"]
            if path in hashes:
                text, digest = proj.read_working(path)
                self.cache[path] = text if digest == hashes[path] else None
            else:
                self.cache[path] = proj.show(self.task["commit"], path)
        return self.cache[path]

    def check(self, item: dict) -> Optional[str]:
        listed = [f["path"] for f in self.task["claim"]["files"]]
        name = item["file"].strip().replace("\\", "/")
        path = next((p for p in listed if p == name or name.endswith("/" + p)
                     or p.endswith("/" + name)), None)
        if path is None:
            return f"{item['file']!r} is not one of the task's files"
        try:
            text = self._text(path)
        except ProjectError as exc:
            return f"{path} could not be read: {exc}"
        if text is None:
            return f"{path} changed since the claim; its quotes cannot be checked"
        finding = {"claim": item["reason"], "file": path, "quote": item["quote"]}
        outcome = adjudication.judge_finding(finding, adjudication.file_sources({path: text}),
                                             {}, frozenset())
        return {adjudication.KEPT: None,
                adjudication.QUOTE: f"the quote is not in {path} at {self.task['commit'][:12]}",
                adjudication.HEDGE: "the reason hedges",
                }.get(outcome, "the item has no checkable content")


def _deny(proj: Project, value, what: str) -> None:
    text = json.dumps(value, ensure_ascii=False)
    for pattern in proj.deny_patterns():
        if pattern.search(text):
            raise TaskError(f"{what} matches {proj.name}'s denylist; nothing was sent")


def _bundle(task: dict) -> dict:
    kind = kinds.KINDS[task["kind"]]
    last = task["attempts"][-1]["outcomes"] if task["attempts"] else []
    return {"task_id": task["task_id"], "kind": task["kind"], "kind_version": kind["version"],
            "instructions": kind["instructions"], "commit": task["commit"],
            "checkout": task["claim"]["checkout"], "files": task["claim"]["files"],
            "findings": [{"index": i, **f} for i, f in enumerate(task["payload"]["findings"])],
            "question": task["payload"]["question"], "attempt": len(task["attempts"]) + 1,
            "rejected": [{"finding": o["finding"], "why": o["why"]} for o in last
                         if o["outcome"] == "rejected"]}


def _view(task: dict) -> dict:
    """What a submitter gets back: the state, and once done, only the items
    whose quotes were checked, the unclear ones, and what failed."""
    view = {"task_id": task["task_id"], "kind": task["kind"], "state": task["state"],
            "commit": task["commit"], "kind_version": task["kind_version"],
            "judge_version": task["judge_version"]}
    if task["state"] == DONE:
        view["result"] = task["result"]
    if task["failure"]:
        view["failure"] = task["failure"]
    if task["claim"] and task["claim"]["missing"]:
        view["missing_files"] = task["claim"]["missing"]
    return view
