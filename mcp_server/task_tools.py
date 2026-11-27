"""The task board's worker tools (ADR-0006): list open tasks, claim one,
and send its answer. Submitters use the CLI (python -m tasks); the board
and its checks are the core's tasks package, which never imports mcp.
"""

from typing import Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_server.guard import current_caller
from tasks.board import Board, TaskError
from tasks.kinds import MAX_FINDINGS, MAX_TEXT, VERDICTS

READS = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                        idempotent_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False,
                         idempotent_hint=False, open_world_hint=False)


class AnswerItem(BaseModel):
    """One item of a second_read answer."""
    finding: int = Field(ge=0, description="the finding's index")
    verdict: Literal[VERDICTS] = Field(description="supported, refuted or unclear")
    file: str = Field("", max_length=1000, description="the listed path the quote is from")
    quote: str = Field("", max_length=MAX_TEXT,
                       description="code copied exactly from that file, whole lines")
    reason: str = Field("", max_length=MAX_TEXT,
                        description="one plain sentence on what the quote shows, no hedge words")


async def _run(fn, *args):
    try:
        return await anyio.to_thread.run_sync(fn, *args)
    except TaskError as exc:
        raise ToolError(str(exc)) from None


def register(server: MCPServer, board: Board) -> None:

    @server.tool(annotations=READS)
    async def list_tasks(state: str = "open", limit: int = 20) -> dict[str, Any]:
        """Tasks on the board, newest first: id, kind, project, commit, state
        (open, claimed, done or failed). Claim an open one with claim_task."""
        rows = await _run(board.list, state or None, max(1, min(int(limit), 200)))
        return {"tasks": rows}

    @server.tool(annotations=WRITES)
    async def claim_task(task_id: str) -> dict[str, Any]:
        """Claim a task and get everything it needs in one result: its
        instructions, the findings, and the files with the path to read each
        from. Calling it again for a task you hold returns the same task, with
        any items sent back for a retry. Then answer with submit_result."""
        return await _run(board.claim, task_id, current_caller.get())

    @server.tool(annotations=WRITES)
    async def submit_result(task_id: str, items: list[AnswerItem]) -> dict[str, Any]:
        """Send the answer to a task you claimed: one item per finding. Each
        supported or refuted item's quote is checked against the file it
        names; a failing item comes back once with the reason (status retry:
        resend those items only), then is reported as unverified."""
        if len(items) > MAX_FINDINGS:
            raise ToolError(f"{len(items)} items, over the {MAX_FINDINGS} limit")
        return await _run(board.submit_result, task_id, current_caller.get(),
                          [i.model_dump() for i in items])
