"""The task board: work a session posts for another agent (Lumo through the
MCP server, or anything with a shell through the CLI), with every answer's
quotes checked against the project's code before the submitter sees it.

Core-side: imports adjudication, never mcp; no network and no model.
"""
