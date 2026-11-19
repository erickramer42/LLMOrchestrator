"""The MCP server: tools to submit a review and read decision records,
and read-only resources for the records and the repo index (ADR-0003).

Reviews are jobs: review_diff returns a debate id at once, and
get_decision reports progress or the finished record. A verdict comes only
from a finished record, so nothing here can approve a review the judge
did not. Every tool call and resource read passes the guard (scopes,
limits, the audit line; ADR-0004). Over stdio, stdout is the protocol:
this module imports debate, never orchestrator, which prints to stdout.
"""

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import anyio
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp_types import ToolAnnotations

import debate
from config import MAX_DEBATE_ROUNDS
from mcp_server import __version__
from mcp_server.guard import AuditLog, Guard, RateLimiter, current_caller
from mcp_server.jobs import (DONE, FAILED, FINISHED, LOST, QueueFull, ReviewQueue,
                             marker_path, record_path)
from mcp_server.tokens import StaticTokenVerifier, TokenStore
from retrieval import CONTEXT_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_FIELD_CHARS = 200_000  # per text field; the input check refuses far less
MAX_WAIT_S = 55            # under the one-minute tool timeout some clients use
MAX_LIST = 200
INDEX_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json")
INDEX_SECTIONS = ("files", "types", "constants", "callsites")
# Hints for clients deciding when to ask before a call: nothing reaches past
# this server and its local models, review_diff writes a record, the rest read
READS = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                        idempotent_hint=True, open_world_hint=False)
SUBMITS = ToolAnnotations(read_only_hint=False, destructive_hint=False,
                          idempotent_hint=False, open_world_hint=False)

INSTRUCTIONS = """\
Multi-agent code review of Havne diffs on local models. review_diff queues
a review and returns its record_id at once; a review takes minutes to tens
of minutes. Follow it with get_decision(record_id, wait_seconds=55) until
status is done, failed or lost. Only final_verdict on a done review is a
verdict; APPROVED_* means approved, anything with MANUAL_REVIEW_REQUIRED
needs a person. Read notes first: index_base_mismatch means the repo
context came from another version of the code."""


@dataclass(frozen=True)
class Settings:
    records_dir: Path
    index_dir: Path
    max_pending: int = 4
    audit_log: Optional[Path] = None    # default: audit.jsonl in records_dir
    tokens_file: Optional[Path] = None  # default: mcp_tokens.json at the repo root
    calls_per_min: int = 120
    reviews_per_hour: int = 20
    max_reviews_per_caller: int = 2

    @property
    def audit_path(self) -> Path:
        return Path(self.audit_log or Path(self.records_dir) / "audit.jsonl")

    @property
    def tokens_path(self) -> Path:
        return Path(self.tokens_file or REPO_ROOT / "mcp_tokens.json")

    @classmethod
    def from_env(cls) -> "Settings":
        """Paths and limits from LLMORCH_* variables, else defaults under the
        repo root: never relative to the working directory."""
        env = os.environ.get
        return cls(
            records_dir=Path(env("LLMORCH_RECORDS_DIR") or REPO_ROOT / "mcp_records"),
            index_dir=Path(env("LLMORCH_INDEX_DIR") or REPO_ROOT / "mcp_indexes"),
            max_pending=int(env("LLMORCH_MAX_PENDING") or 4),
            audit_log=Path(env("LLMORCH_AUDIT_LOG")) if env("LLMORCH_AUDIT_LOG") else None,
            tokens_file=Path(env("LLMORCH_TOKENS_FILE")) if env("LLMORCH_TOKENS_FILE") else None,
            calls_per_min=int(env("LLMORCH_RATE_PER_MIN") or 120),
            reviews_per_hour=int(env("LLMORCH_REVIEWS_PER_HOUR") or 20),
            max_reviews_per_caller=int(env("LLMORCH_MAX_REVIEWS_PER_CALLER") or 2))


def _check_id(record_id: str) -> str:
    if not debate.DEBATE_ID_PATTERN.fullmatch(record_id or ""):
        raise ToolError(f"not a review id: {record_id!r} (expected debate_YYYYMMDD_HHMMSS_xxxxxx)")
    return record_id


def _check_text(name: str, value: str) -> None:
    if len(value) > MAX_FIELD_CHARS:
        raise ToolError(f"{name} is {len(value)} chars, over the {MAX_FIELD_CHARS} limit; "
                        "split the change into smaller diffs")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"cannot read {path.name}: {type(exc).__name__}") from None


def _notes(meta: dict, outputs: dict) -> list:
    """What a reader must know before the verdict, the index mismatch first."""
    notes = []
    pack = meta.get("repo_context_pack") or {}
    mismatched = (pack.get("base_check") or {}).get("mismatched")
    if mismatched:
        notes.append(f"index_base_mismatch: the repo context index holds another version "
                     f"of {', '.join(mismatched)}; its pack may describe other code")
    reason = (meta.get("input_check") or {}).get("reason")
    if reason:
        notes.append(f"input_refused: {reason}")
    if pack.get("error"):
        notes.append(f"retrieval_error: {pack['error']}")
    for failure in outputs.get("agent_failures") or []:
        notes.append(f"agent_failure: {failure}")
    return notes


def summarize_record(record: dict, include_record: bool = False) -> dict:
    """A finished review: its verdict, the final round's findings after the
    guardrails, and its provenance."""
    meta = record.get("metadata") or {}
    outputs = record.get("outputs") or {}
    inputs = record.get("inputs") or {}
    history = outputs.get("round_history") or []
    last = history[-1] if history else {}
    rev = last.get("reviewer") or {}
    eng = last.get("auto_engineer") or {}
    summary = {
        "record_id": meta.get("debate_id"),
        "status": DONE,
        "final_verdict": outputs.get("final_verdict"),
        "notes": _notes(meta, outputs),
        "rounds_completed": len(history),
        "findings": {
            "reviewer": {k: rev.get(k) or [] for k in ("blockers", "questions", "nits")},
            "engineer": {k: eng.get(k) or [] for k in ("blockers", "concerns", "questions")},
        },
        "created_utc": meta.get("created_utc"),
        "prompt_version": meta.get("prompt_version"),
        "judge_version": meta.get("judge_version"),
        "models": meta.get("models_used"),
        "interface": meta.get("interface") or {"name": "cli"},
        "diff_sha256": inputs.get("diff_sha256"),
        "context_sha256": inputs.get("context_sha256"),
        "resource": f"decision://{meta.get('debate_id')}",
        "server_version": __version__,
    }
    tokens = _model_tokens(history)
    if tokens["attempts"]:
        summary["model_tokens"] = tokens
    if include_record:
        summary["record"] = record
    return summary


def _model_tokens(history: list) -> dict:
    """Prompt and output tokens over every agent attempt of a record."""
    out = {"prompt": 0, "output": 0, "attempts": 0}
    for entry in history:
        for attempts in (entry.get("telemetry") or {}).values():
            for a in attempts or []:
                out["attempts"] += 1
                out["prompt"] += a.get("prompt_eval_count") or 0
                out["output"] += a.get("eval_count") or 0
    return out


class Tribunal:
    """The server's state: settings and the review queue."""

    def __init__(self, settings: Settings, queue: Optional[ReviewQueue] = None,
                 transport: str = "stdio"):
        self.settings = settings
        self.interface = {"name": "mcp", "server_version": __version__, "transport": transport}
        self.queue = queue or ReviewQueue(settings.records_dir, self.interface,
                                          settings.max_pending)

    def index_path(self, index_name: Optional[str]) -> Optional[str]:
        if not index_name:
            return None
        if not INDEX_NAME.fullmatch(index_name):
            raise ToolError(f"index_name must be a .json file name with no path: {index_name!r}")
        path = self.settings.index_dir / index_name
        if not path.is_file():
            raise ToolError(f"no index named {index_name!r} in the server's index directory")
        return str(path)

    def describe(self, record_id: str, include_record: bool = False) -> dict:
        """A review's state: live job, finished record, or marker."""
        records = self.settings.records_dir
        live = self.queue.status(record_id)
        if live is not None and live["state"] not in FINISHED:
            return {"record_id": record_id, "status": live["state"],
                    "final_verdict": None, "round": live["round"],
                    "agent": live["agent"], "queue_position": live.get("queue_position"),
                    "submitted_utc": live["submitted_utc"],
                    "started_utc": live["started_utc"], "server_version": __version__}
        if live is not None and live["state"] == FAILED:
            return self._failed(record_id, live["error"])
        path = record_path(records, record_id)
        if path.is_file():
            return summarize_record(_read_json(path), include_record)
        marker = marker_path(records, record_id)
        if marker.is_file():
            content = _read_json(marker)
            if content.get("state") == FAILED:
                return self._failed(record_id, content.get("error"))
            return {"record_id": record_id, "status": LOST, "final_verdict": None,
                    "notes": ["lost: the server stopped before this review finished; "
                              "no record was written. Submit it again."],
                    "submitted_utc": content.get("submitted_utc"),
                    "server_version": __version__}
        raise ToolError(f"unknown review {record_id}: no queued, running or recorded "
                        "review on this server")

    @staticmethod
    def _failed(record_id: str, error: Optional[str]) -> dict:
        return {"record_id": record_id, "status": FAILED, "final_verdict": None,
                "notes": [f"server_error: {error}; no verdict was reached"],
                "server_version": __version__}

    def list_reviews(self, limit: int, since: Optional[datetime]) -> list:
        """Live jobs, records and markers, newest first."""
        rows = []
        for job in self.queue.live():
            rows.append({"record_id": job["record_id"], "status": job["state"],
                         "final_verdict": None, "time_utc": job["submitted_utc"]})
        seen = {r["record_id"] for r in rows}
        records = self.settings.records_dir
        for path in sorted(records.glob("decision_debate_*.json"), reverse=True):
            record_id = path.stem[len("decision_"):]
            if record_id in seen or not debate.DEBATE_ID_PATTERN.fullmatch(record_id):
                continue
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            meta, inputs = rec.get("metadata") or {}, rec.get("inputs") or {}
            rows.append({"record_id": record_id, "status": DONE,
                         "final_verdict": (rec.get("outputs") or {}).get("final_verdict"),
                         "time_utc": meta.get("created_utc"),
                         "diff_sha256": inputs.get("diff_sha256"),
                         "context_sha256": inputs.get("context_sha256"),
                         "proposal": (inputs.get("original_proposal") or "")[:120]})
            seen.add(record_id)
        for path in sorted(records.glob("pending_debate_*.json"), reverse=True):
            record_id = path.stem[len("pending_"):]
            if record_id in seen or not debate.DEBATE_ID_PATTERN.fullmatch(record_id):
                continue
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            rows.append({"record_id": record_id,
                         "status": FAILED if content.get("state") == FAILED else LOST,
                         "final_verdict": None,
                         "time_utc": content.get("submitted_utc") or content.get("finished_utc"),
                         "diff_sha256": content.get("diff_sha256")})
        if since is not None:
            rows = [r for r in rows if _parse_time(r.get("time_utc")) >= since]
        rows.sort(key=lambda r: _parse_time(r.get("time_utc")), reverse=True)
        return rows[:limit]


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_time(value: Optional[str]) -> datetime:
    if not value:
        return _EPOCH
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return _EPOCH
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def build_server(settings: Optional[Settings] = None,
                 queue: Optional[ReviewQueue] = None, transport: str = "stdio",
                 base_url: Optional[str] = None,
                 limiter: Optional[RateLimiter] = None) -> MCPServer:
    """The server with its tools, resources and guard; the queue's worker
    starts here. Over HTTP every request needs a token from the settings'
    token file. queue and limiter replace the defaults (tests)."""
    settings = settings or Settings.from_env()
    tribunal = Tribunal(settings, queue, transport)
    tribunal.queue.start()
    guard = Guard(transport, AuditLog(settings.audit_path),
                  limiter or RateLimiter(settings.calls_per_min, settings.reviews_per_hour),
                  tribunal.queue.active_count, settings.max_reviews_per_caller)
    auth = {}
    if transport == "http":
        # No Protected Resource Metadata is served (resource_server_url None),
        # so issuer_url is never published (ADR-0004)
        auth = {"token_verifier": StaticTokenVerifier(TokenStore(settings.tokens_path)),
                "auth": AuthSettings(issuer_url=base_url or "http://127.0.0.1",
                                     resource_server_url=None)}
    server = MCPServer(name="llm-orchestrator", version=__version__,
                       instructions=INSTRUCTIONS, middleware=[guard], **auth)
    server.tribunal = tribunal  # type: ignore[attr-defined]
    server.guard = guard  # type: ignore[attr-defined]

    @server.tool(annotations=SUBMITS)
    async def review_diff(proposal: str, diff: str = "", context: str = "",
                          header: bool = False,
                          index_name: Optional[str] = None) -> dict[str, Any]:
        """Queue a multi-agent review of a unified diff (or, with header=true,
        a header given as context) and return its record_id at once.

        proposal: what the change does and why. diff: the unified diff text.
        context: extra source text, shown to the reviewers. index_name: a
        repo index file in the server's index directory, built from the
        diff's base; by default the committed index is used. Input that
        cannot fit the models' context window is refused, never truncated.
        A review takes minutes to tens of minutes: follow it with
        get_decision(record_id, wait_seconds=55) until status is done,
        failed or lost."""
        for name, value in (("proposal", proposal), ("diff", diff), ("context", context)):
            _check_text(name, value)
        index_path = tribunal.index_path(index_name)
        caller = current_caller.get()
        check = await anyio.to_thread.run_sync(
            debate.check_input, proposal, diff, context, header, index_path)
        if check["verdict"] is not None:
            # Refused without a model call; record it now, not after the queue.
            result = await anyio.to_thread.run_sync(lambda: debate.run_debate(
                proposal, diff, context, header_artifact=header, index_path=index_path,
                records_dir=tribunal.settings.records_dir,
                interface={**tribunal.interface, "caller": caller}))
            return tribunal.describe(result["debate_id"])
        try:
            record_id = tribunal.queue.submit(proposal, diff, context, header, index_path,
                                              caller=caller)
        except QueueFull as exc:
            raise ToolError(f"busy: {exc}; try again after a review finishes") from None
        notes = []
        if check.get("index_base_mismatch"):
            notes.append("index_base_mismatch: the repo context index holds another version "
                         f"of {', '.join(check['index_base_mismatch'])}; pass index_name "
                         "with an index built from the diff's base")
        if check.get("retrieval_error"):
            notes.append(f"retrieval_error: {check['retrieval_error']}")
        state = tribunal.describe(record_id)  # may already be finished
        state["notes"] = notes + [n for n in state.get("notes", []) if n not in notes]
        return state

    @server.tool(annotations=READS)
    async def get_decision(record_id: str, wait_seconds: int = 0,
                           include_record: bool = False,
                           ctx: Optional[Context] = None) -> dict[str, Any]:
        """A review's status (queued, running, done, failed or lost) and, once
        done, its final_verdict and findings. wait_seconds (up to 55) waits
        for the review to finish, sending progress meanwhile; call again
        while status is queued or running. Only a done review's final_verdict
        is a verdict: APPROVED_* approves, any MANUAL_REVIEW_REQUIRED needs a
        person. Read notes first. include_record adds the full decision record."""
        _check_id(record_id)
        deadline = time.monotonic() + max(0, min(int(wait_seconds), MAX_WAIT_S))
        state = tribunal.describe(record_id, include_record)
        while state["status"] not in FINISHED and time.monotonic() < deadline:
            seen = (state["status"], state.get("round"), state.get("agent"))
            await anyio.to_thread.run_sync(tribunal.queue.wait_for_change, record_id, seen,
                                           min(5.0, max(0.0, deadline - time.monotonic())))
            state = tribunal.describe(record_id, include_record)
            if ctx is not None and state["status"] not in FINISHED and state.get("round"):
                step = 2 * (state["round"] - 1) + (state["agent"] == "auto_engineer")
                await ctx.report_progress(step, 2 * MAX_DEBATE_ROUNDS,
                                          f"round {state['round']}: {state['agent']}")
        return state

    @server.tool(annotations=READS)
    async def list_decisions(limit: int = 20,
                             since: Optional[str] = None) -> dict[str, Any]:
        """Recent reviews on this server, newest first: status, verdict and
        input hashes. since is an ISO 8601 date or time (UTC if no offset)."""
        since_dt = None
        if since:
            since_dt = _parse_time(since)
            if since_dt == _EPOCH:
                raise ToolError(f"since is not an ISO 8601 date or time: {since!r}")
        rows = await anyio.to_thread.run_sync(
            tribunal.list_reviews, max(1, min(int(limit), MAX_LIST)), since_dt)
        return {"reviews": rows, "server_version": __version__}

    @server.resource("decision://{record_id}", mime_type="application/json",
                     description="A finished review's full decision record.")
    def decision_record(record_id: str) -> str:
        if not debate.DEBATE_ID_PATTERN.fullmatch(record_id):
            raise ResourceNotFoundError(f"not a review id: {record_id!r}")
        path = record_path(tribunal.settings.records_dir, record_id)
        if not path.is_file():
            raise ResourceNotFoundError(f"no record for {record_id}")
        return path.read_text(encoding="utf-8")

    def index_section(section: Optional[str]):
        def read() -> str:
            index = json.loads(Path(CONTEXT_PATH).read_text(encoding="utf-8"))
            if section is None:
                return json.dumps({k: v for k, v in index.items()
                                   if k not in INDEX_SECTIONS}, indent=2)
            return json.dumps(index.get(section, []), indent=2)
        return read

    server.resource("index://info", name="index-info", mime_type="application/json",
                    description="The committed repo index: version, source commit, summary model."
                    )(index_section(None))
    for section in INDEX_SECTIONS:
        server.resource(f"index://{section}", name=f"index-{section}",
                        mime_type="application/json",
                        description=f"The committed repo index's {section}."
                        )(index_section(section))
    return server
