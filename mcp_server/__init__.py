"""MCP server for the tribunal (ADR-0003): reviews submitted as jobs, the
decision records and the repo index, over the official MCP Python SDK.

The package imports the core (debate, adjudication, retrieval); no core
module imports it or the SDK. Install with requirements-mcp.txt; run with
`python -m mcp_server` from the repo root, or `python <repo>/mcp_server`
from anywhere.
"""

__version__ = "0.3.0"
