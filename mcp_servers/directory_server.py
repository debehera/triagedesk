"""Directory MCP server (stdio): get_user, find_resource, check_access.

Run in the MCP Inspector:  mcp dev mcp_servers/directory_server.py
Or let a client start it:  see tests/test_directory_stdio.py

IMPORTANT: this is a stdio server. stdout carries the protocol messages, so never use print()
here or in anything it imports. Log to stderr (mcp_servers.common.log).
"""

import sys
from pathlib import Path

# Make `mcp_servers` and `src` importable when this file is started as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_servers.directory_logic import check_access, find_resource, get_user  # noqa: E402

mcp = FastMCP("directory")

for _tool in (get_user, find_resource, check_access):
    mcp.tool()(_tool)

if __name__ == "__main__":
    mcp.run()
