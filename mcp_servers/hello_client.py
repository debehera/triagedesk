"""Minimal MCP client that starts hello_server.py over stdio and calls its tools.

Run:  python mcp_servers/hello_client.py

This is the same pattern src/mcp_client.py will use for the real servers.
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).with_name("hello_server.py")


async def main() -> None:
    # sys.executable makes sure the server runs in the same virtual environment.
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools exposed by the server:")
            for tool in tools.tools:
                print(f"  - {tool.name}: {(tool.description or '').splitlines()[0]}")
                print(f"    input schema: {tool.inputSchema}")

            print("\nCalling add(2, 3):")
            result = await session.call_tool("add", {"a": 2, "b": 3})
            print(" ", [block.text for block in result.content if hasattr(block, "text")])

            print("\nCalling lookup_ticket_status('T-9999') (expected NOT_FOUND):")
            result = await session.call_tool("lookup_ticket_status", {"ticket_id": "T-9999"})
            print(" ", [block.text for block in result.content if hasattr(block, "text")])


if __name__ == "__main__":
    asyncio.run(main())
