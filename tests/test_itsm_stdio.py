"""Real stdio round trip: start itsm_server.py as a child process and talk MCP to it.

Passing proves the handshake works (so stdout is clean), the four tools are exposed with
descriptions and argument schemas, and state persists across calls within one server process.
"""

import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent.parent / "mcp_servers" / "itsm_server.py"
REQUIRED = {
    "search_kb": ["query"],
    "get_ticket": ["ticket_id"],
    "update_ticket": ["ticket_id", "status", "note"],
    "add_comment": ["ticket_id", "text", "visibility"],
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
    for name in ("update_ticket", "add_comment"):
        assert "Write operation" in tools[name].description


async def test_read_then_write_round_trip(params):
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            found = await call(session, "search_kb", {"query": "vpn authentication failed"})
            before = await call(session, "get_ticket", {"ticket_id": "T-1001"})
            updated = await call(
                session,
                "update_ticket",
                {"ticket_id": "T-1001", "status": "resolved", "note": "Fixed via KB-003"},
            )
            after = await call(session, "get_ticket", {"ticket_id": "T-1001"})
            comment = await call(
                session,
                "add_comment",
                {"ticket_id": "T-1001", "text": "Please retry.", "visibility": "requester"},
            )
            bad = await call(
                session,
                "update_ticket",
                {"ticket_id": "T-1001", "status": "closed", "note": ""},
            )
    assert found["data"]["matches"][0]["id"] == "KB-003"
    assert before["data"]["status"] == "open"
    assert updated == {"ok": True, "data": {"ticket_id": "T-1001", "status": "resolved"}}
    assert after["data"]["status"] == "resolved" and after["data"]["notes"] == ["Fixed via KB-003"]
    assert comment["data"]["comment_id"] == "C-0001"
    assert bad["ok"] is False and bad["error"]["code"] == "INVALID_INPUT"


async def test_each_server_process_starts_from_the_seed(params):
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            seen = await call(session, "get_ticket", {"ticket_id": "T-1001"})
    assert seen["data"]["status"] == "open"


async def test_fault_injection_reaches_the_child_process():
    faulty = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
        env={"FAULT_INJECT": '{"search_kb": "TIMEOUT_ONCE"}'},
    )
    async with stdio_client(faulty) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            first = await call(session, "search_kb", {"query": "vpn"})
            second = await call(session, "search_kb", {"query": "vpn"})
    assert first["error"]["code"] == "TIMEOUT" and first["error"]["retryable"] is True
    assert second["ok"] is True
