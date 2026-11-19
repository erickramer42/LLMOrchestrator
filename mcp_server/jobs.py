"""The review queue: one worker thread runs debates one at a time, since
they share one GPU, and a bounded queue holds the rest (ADR-0003).

Jobs live in memory. Each submission writes a pending marker beside the
records, and the debate's record supersedes it, so after a restart a
review with a marker and no record is reported as lost. No SDK import:
this module is plain threads and files.
"""

import json
import os
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import debate

QUEUED, RUNNING, DONE, FAILED, LOST = "queued", "running", "done", "failed", "lost"
FINISHED = (DONE, FAILED, LOST)


class QueueFull(Exception):
    """The queue holds max_pending reviews already."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_path(records_dir: Path, record_id: str) -> Path:
    return Path(records_dir) / f"decision_{record_id}.json"


def marker_path(records_dir: Path, record_id: str) -> Path:
    return Path(records_dir) / f"pending_{record_id}.json"


class ReviewQueue:
    """Runs submitted debates in order on one worker thread.

    run is debate.run_debate or a stand-in with its signature; interface
    is stamped into every record."""

    def __init__(self, records_dir: Path, interface: dict,
                 max_pending: int = 4,
                 run: Callable[..., dict] = debate.run_debate):
        self.records_dir = Path(records_dir)
        self.interface = dict(interface)
        self._run = run
        self._pending: "queue.Queue[str]" = queue.Queue(maxsize=max_pending)
        self._jobs: dict = {}
        self._cond = threading.Condition()
        self._worker: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = threading.Thread(target=self._work, name="review-worker",
                                            daemon=True)
            self._worker.start()

    def submit(self, proposal: str, code_diff: str, code_context: str = "",
               header_artifact: bool = False,
               index_path: Optional[str] = None, caller: str = "stdio") -> str:
        """Queue a review and return its debate id; QueueFull if full."""
        record_id = debate.new_debate_id()
        job = {"record_id": record_id, "state": QUEUED, "caller": caller, "round": None,
               "agent": None, "submitted_utc": _now(), "started_utc": None,
               "finished_utc": None, "error": None, "result": None,
               "args": (proposal, code_diff, code_context, header_artifact,
                        index_path)}
        with self._cond:
            if self._pending.full():
                raise QueueFull(f"{self._pending.maxsize} reviews already wait")
            # The marker precedes the worker, which may finish and replace it at once.
            self._write_marker(record_id, {
                "record_id": record_id, "state": QUEUED, "caller": caller,
                "submitted_utc": job["submitted_utc"],
                "diff_sha256": debate.text_sha256(code_diff) if code_diff else None,
                "context_sha256": debate.text_sha256(code_context) if code_context else None})
            self._jobs[record_id] = job
            self._pending.put_nowait(record_id)  # only submit() puts, under the lock
        return record_id

    def status(self, record_id: str) -> Optional[dict]:
        """A live job's state without its inputs, or None if not in memory."""
        with self._cond:
            job = self._jobs.get(record_id)
            if job is None:
                return None
            view = {k: v for k, v in job.items() if k != "args"}
            if job["state"] == QUEUED:
                view["queue_position"] = 1 + sum(
                    1 for j in self._jobs.values()
                    if j["state"] == QUEUED and j["submitted_utc"] < job["submitted_utc"])
            return view

    def active_count(self, caller: str) -> int:
        """The caller's reviews that are queued or running."""
        with self._cond:
            return sum(1 for j in self._jobs.values()
                       if j["caller"] == caller and j["state"] in (QUEUED, RUNNING))

    def live(self) -> list:
        """Every queued or running job, oldest first."""
        with self._cond:
            ids = [j["record_id"] for j in self._jobs.values()
                   if j["state"] in (QUEUED, RUNNING)]
        return [s for s in (self.status(i) for i in ids) if s]

    def wait_for_change(self, record_id: str, seen: tuple, timeout: float) -> None:
        """Block until the job's (state, round, agent) differs from seen,
        or timeout seconds pass."""
        def changed():
            job = self._jobs.get(record_id)
            return job is None or (job["state"], job["round"], job["agent"]) != seen
        with self._cond:
            self._cond.wait_for(changed, timeout)

    def _write_marker(self, record_id: str, content: dict) -> None:
        """Replace the marker whole, so a reader never sees half of one."""
        self.records_dir.mkdir(parents=True, exist_ok=True)
        path = marker_path(self.records_dir, record_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(content, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _update(self, record_id: str, **fields) -> None:
        with self._cond:
            self._jobs[record_id].update(fields)
            self._cond.notify_all()

    def _work(self) -> None:
        while True:
            record_id = self._pending.get()
            try:
                self._run_one(record_id)
            finally:
                self._pending.task_done()

    def _run_one(self, record_id: str) -> None:
        proposal, code_diff, code_context, header, index_path = self._jobs[record_id]["args"]
        self._update(record_id, state=RUNNING, started_utc=_now())
        try:
            result = self._run(
                proposal, code_diff, code_context, header_artifact=header,
                index_path=index_path, debate_id=record_id,
                records_dir=self.records_dir,
                on_progress=lambda e: self._update(record_id, round=e.get("round"),
                                                   agent=e.get("agent")),
                interface={**self.interface, "caller": self._jobs[record_id]["caller"]})
        except Exception as exc:  # a server fault, not a verdict: keep it answerable
            error = f"{type(exc).__name__}: {exc}"
            try:
                self._write_marker(record_id, {"record_id": record_id, "state": FAILED,
                                               "error": error, "finished_utc": _now()})
            except OSError:
                pass
            self._update(record_id, state=FAILED, error=error, finished_utc=_now())
            return
        try:
            marker_path(self.records_dir, record_id).unlink()
        except OSError:
            pass
        self._update(record_id, state=DONE, result=result, finished_utc=_now())

    def join(self, timeout: float = 30.0) -> None:
        """Wait until the queue is empty and the worker idle (tests)."""
        deadline = time.monotonic() + timeout
        while self.live() and time.monotonic() < deadline:
            time.sleep(0.01)
