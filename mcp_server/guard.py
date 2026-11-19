"""Scopes, limits and the audit log around every tool call and resource
read, on both transports (ADR-0004).

One server middleware: it names the caller (the token's id over HTTP,
`stdio` otherwise), refuses a call outside the caller's scopes or over a
limit, runs the call, and appends one audit line. The diff, context and
proposal never reach the log: only their SHA-256 and length do, and a
caller is named by its token's id, never the token.
"""

import contextvars
import hashlib
import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.shared.exceptions import MCPError
from mcp_types import INVALID_REQUEST, CallToolResult, TextContent
from pydantic import BaseModel

from mcp_server import __version__
from mcp_server.tokens import READ, REVIEW, SCOPES

REDACTED_ARGS = ("proposal", "diff", "context")
REVIEW_TOOLS = ("review_diff",)
AUDITED = ("tools/call", "resources/read")
STDIO_CALLER = "stdio"

# The caller of the request being handled, for the tools (review_diff
# records who submitted a review)
current_caller: contextvars.ContextVar[str] = contextvars.ContextVar("caller", default=STDIO_CALLER)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(arguments: dict) -> dict:
    """Arguments for the log: reviewed text by hash and length only."""
    out = {}
    for key, value in (arguments or {}).items():
        if key in REDACTED_ARGS and isinstance(value, str):
            out[key] = {"sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                        "chars": len(value)}
        elif key in REDACTED_ARGS:
            out[key] = {"type": type(value).__name__}
        else:
            out[key] = value
    return out


class AuditLog:
    """Append-only JSON lines; one write per line under a lock."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def write(self, entry: dict) -> None:
        line = json.dumps({"time_utc": _now(), "server_version": __version__, **entry},
                          ensure_ascii=False, default=str)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")


class RateLimiter:
    """Sliding windows per caller: calls a minute and review submissions an
    hour. In memory: a restart resets them."""

    def __init__(self, calls_per_min: int, reviews_per_hour: int,
                 clock: Callable[[], float] = time.monotonic):
        self.calls_per_min = calls_per_min
        self.reviews_per_hour = reviews_per_hour
        self.clock = clock
        self._calls = defaultdict(deque)
        self._reviews = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _take(window: deque, limit: int, span: float, now: float) -> Optional[float]:
        """None if a slot was taken, else seconds until one frees."""
        while window and window[0] <= now - span:
            window.popleft()
        if len(window) >= limit:
            return window[0] + span - now
        window.append(now)
        return None

    def take_call(self, caller: str) -> Optional[float]:
        with self._lock:
            return self._take(self._calls[caller], self.calls_per_min, 60.0, self.clock())

    def take_review(self, caller: str) -> Optional[float]:
        with self._lock:
            return self._take(self._reviews[caller], self.reviews_per_hour, 3600.0, self.clock())


def _as_dict(result) -> dict:
    if isinstance(result, BaseModel):
        return result.model_dump(by_alias=True, exclude_none=True)
    return dict(result or {})


def _first_line(result: dict) -> str:
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            return (block.get("text") or "").splitlines()[0][:200] if block.get("text") else ""
    return ""


class Guard:
    """The server middleware. transport is "stdio" or "http"; over HTTP a
    request without an accepted token never reaches here (the SDK's bearer
    middleware answers 401), and one that does anyway is refused."""

    def __init__(self, transport: str, audit: AuditLog, limiter: RateLimiter,
                 active_reviews: Callable[[str], int], max_reviews_per_caller: int):
        self.transport = transport
        self.audit = audit
        self.limiter = limiter
        self.active_reviews = active_reviews
        self.max_reviews_per_caller = max_reviews_per_caller

    def _caller(self):
        token = get_access_token()
        if token is not None:
            return token.client_id, set(token.scopes)
        if self.transport == "stdio":
            return STDIO_CALLER, set(SCOPES)
        return None, set()

    async def __call__(self, ctx, call_next):
        if ctx.request_id is None or ctx.method not in AUDITED:
            return await call_next(ctx)
        started = time.monotonic()
        params = dict(ctx.params or {})
        is_tool = ctx.method == "tools/call"
        name = params.get("name") if is_tool else None
        caller, scopes = self._caller()
        entry = {"transport": self.transport, "caller": caller, "method": ctx.method}
        if is_tool:
            entry.update(tool=name, arguments=redact(params.get("arguments") or {}))
        else:
            entry["uri"] = params.get("uri")

        def refuse(outcome: str, message: str):
            entry.update(outcome=outcome, error=message,
                         duration_ms=round((time.monotonic() - started) * 1000))
            self.audit.write(entry)
            if is_tool:
                return CallToolResult(content=[TextContent(type="text", text=message)],
                                      is_error=True)
            raise MCPError(code=INVALID_REQUEST, message=message)

        if caller is None:
            return refuse("unauthenticated", "unauthenticated: no accepted token")
        needed = REVIEW if name in REVIEW_TOOLS else READ
        if needed not in scopes:
            return refuse("insufficient_scope",
                          f"insufficient_scope: {name or ctx.method} needs the {needed!r} scope")
        wait = self.limiter.take_call(caller)
        if wait is not None:
            return refuse("rate_limited", f"rate_limited: over {self.limiter.calls_per_min} "
                          f"calls a minute; retry in {wait:.0f} s")
        if name in REVIEW_TOOLS:
            active = self.active_reviews(caller)
            if active >= self.max_reviews_per_caller:
                return refuse("rate_limited", f"rate_limited: {active} of your reviews are "
                              f"queued or running (limit {self.max_reviews_per_caller}); "
                              "retry when one finishes")
            wait = self.limiter.take_review(caller)
            if wait is not None:
                return refuse("rate_limited", f"rate_limited: over {self.limiter.reviews_per_hour} "
                              f"reviews an hour; retry in {wait:.0f} s")

        reset = current_caller.set(caller)
        try:
            result = await call_next(ctx)
        except Exception as exc:
            entry.update(outcome="error", error=f"{type(exc).__name__}: "
                         f"{str(exc).splitlines()[0][:200] if str(exc) else ''}",
                         duration_ms=round((time.monotonic() - started) * 1000))
            self.audit.write(entry)
            raise
        finally:
            current_caller.reset(reset)
        data = _as_dict(result)
        entry["duration_ms"] = round((time.monotonic() - started) * 1000)
        if is_tool and data.get("isError"):
            entry.update(outcome="tool_error", error=_first_line(data))
        else:
            entry["outcome"] = "ok"
            structured = data.get("structuredContent") or {}
            for key in ("record_id", "status", "final_verdict", "model_tokens"):
                if structured.get(key) is not None:
                    entry[key] = structured[key]
        self.audit.write(entry)
        return result


class HttpRefusals:
    """ASGI wrapper that writes an audit line for each HTTP request refused
    before MCP: 401 (no accepted token), 403 (an Origin not allowed), 421
    (a Host not allowed). Lifespan and other scopes pass through."""

    REFUSED = (401, 403, 421)

    def __init__(self, app, audit: AuditLog):
        self.app = app
        self.audit = audit

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        status = {}

        async def watch(message):
            if message.get("type") == "http.response.start":
                status["code"] = message.get("status")
            await send(message)
        await self.app(scope, receive, watch)
        if status.get("code") in self.REFUSED:
            client = scope.get("client")
            self.audit.write({"transport": "http", "caller": None, "event": "http_refused",
                              "status": status["code"], "method": scope.get("method"),
                              "path": scope.get("path"),
                              "client": client[0] if client else None})
