"""Hello-world MCP server for learning (Day 1-2).

Run in the MCP Inspector:   mcp dev mcp_servers/hello_server.py
Or call it from Python:     python mcp_servers/hello_client.py

IMPORTANT: this is a stdio server. Never use print() here, because stdout is
reserved for protocol messages. Log to stderr instead.
"""

import sys
from typing import Literal

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hello")

# Tiny fake data set so the third tool looks like the real ITSM tools we will build later.
_TICKETS = {
    "T-1001": "open",
    "T-1002": "resolved",
}


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return the sum.

    Use this when you need exact integer addition. Does not handle decimals.
    """
    return a + b


@mcp.tool()
def get_greeting(name: str, style: Literal["formal", "casual"] = "casual") -> str:
    """Return a greeting for a person.

    Args:
        name: The person's name.
        style: "formal" or "casual". Defaults to casual.
    """
    if style == "formal":
        return f"Good day, {name}."
    return f"Hey {name}!"


@mcp.tool()
def lookup_ticket_status(ticket_id: str) -> dict:
    """Look up the status of a ticket by id (for example T-1001).

    Returns {"ok": true, "data": {...}} on success, or
    {"ok": false, "error": {...}} if the ticket does not exist.
    This follows the error contract we will use in the real servers.
    """
    status = _TICKETS.get(ticket_id)
    if status is None:
        return {
            "ok": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"No ticket with id {ticket_id}",
                "retryable": False,
            },
        }
    return {"ok": True, "data": {"ticket_id": ticket_id, "status": status}}


if __name__ == "__main__":
    print("hello server starting (stderr only)", file=sys.stderr)
    mcp.run()  # stdio transport by default
