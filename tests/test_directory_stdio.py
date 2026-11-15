"""Real stdio round trip: start directory_server.py as a child process and talk MCP to it.

If the server printed anything to stdout besides protocol messages, the handshake would fail,
so a passing test also proves stdout is clean (CLAUDE.md rule 5).
"""

import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent.parent / "mcp_servers" / "directory_server.py"
REQUIRED = {
    "get_user": ["user_id"],
    "find_resource": ["query"],
    "check_access": ["user_id", "resource_id"],
}


async def call(session: ClientSession, name: str, args: dict) -> dict:
    result = await session.call_tool(name, args)
    return json.loads(result.content[0].text)


@pytest.fixture
def params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[str(SERVER)])


async def test_tools_listed_with_descriptions_and_schemas(params):
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
    assert set(tools) == set(REQUIRED)
    for name, required in REQUIRED.items():
        assert (tools[name].description or "").strip(), name
        assert sorted(tools[name].inputSchema["required"]) == sorted(required), name


async def test_success_and_error_round_trip(params):
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            good = await call(session, "get_user", {"user_id": "u-104"})
            bad = await call(session, "check_access", {"user_id": "u-108", "resource_id": "r-99"})
            found = await call(session, "find_resource", {"query": "the finance share"})
    assert good["ok"] is True and good["data"]["name"] == "Dev Patel"
    assert bad["ok"] is False and bad["error"]["code"] == "NOT_FOUND"
    assert found["data"]["resources"][0]["id"] == "r-05"


async def test_fault_injection_reaches_the_child_process(params):
    faulty = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
        env={"FAULT_INJECT": '{"get_user": "TIMEOUT"}'},
    )
    async with stdio_client(faulty) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await call(session, "get_user", {"user_id": "u-101"})
    assert result["error"]["code"] == "TIMEOUT" and result["error"]["retryable"] is True
