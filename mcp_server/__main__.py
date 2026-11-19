"""Run the MCP server over stdio: `python -m mcp_server` from the repo
root, or `python <repo>/mcp_server` from any directory."""

import sys
from pathlib import Path

# The core modules sit at the repo root, which a client's working
# directory need not be.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_server.server import main  # noqa: E402

if __name__ == "__main__":
    main()
