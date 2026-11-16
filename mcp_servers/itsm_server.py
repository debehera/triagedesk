"""ITSM MCP server (stdio): search_kb, get_ticket, update_ticket, add_comment.

Run in the MCP Inspector:  mcp dev mcp_servers/itsm_server.py
Or let a client start it:  see tests/test_itsm_stdio.py

IMPORTANT: this is a stdio server. stdout carries the protocol messages, so never use print()
here or in anything it imports. Log to stderr (mcp_servers.common.log).

update_ticket and add_comment are registered here so the coordinator's commit step can call
them, but the model is never given them (docs/API.md section 7, ADR-014): the allow-list is
enforced by the hub on Day 5 and the pre-tool guardrail on Day 7.
"""

import sys
from pathlib import Path

# Make `mcp_servers` and `src` importable when this file is started as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_servers.itsm_logic import add_comment, get_ticket, search_kb, update_ticket  # noqa: E402

mcp = FastMCP("itsm")

for _tool in (search_kb, get_ticket, update_ticket, add_comment):
    mcp.tool()(_tool)

if __name__ == "__main__":
    mcp.run()
