"""Tests for src/mcp_hub.py. Most tests start the REAL servers over stdio (about a second each)."""

import asyncio
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.mcp_hub import (
    READ_ONLY_TOOLS,
    WRITE_TOOLS,
    HubError,
    McpHub,
    _parse_envelope,
    build_registry,
)

SETTINGS = Settings.from_env({})


class Sleeps:
    """Records back-off sleeps instead of waiting."""

    def __init__(self):
        self.values: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.values.append(seconds)


# ---------- real servers ----------


async def test_starts_both_servers_and_lists_seven_tools():
    async with McpHub.start(SETTINGS) as hub:
        assert hub.tool_names == sorted(READ_ONLY_TOOLS | WRITE_TOOLS)
        assert len(hub.tool_names) == 7


async def test_tool_defs_are_filtered_sorted_and_api_shaped():
    async with McpHub.start(SETTINGS) as hub:
        defs = hub.tool_defs(READ_ONLY_TOOLS)
        assert [d["name"] for d in defs] == sorted(READ_ONLY_TOOLS)
        assert len(defs) == 5
        for d in defs:
            assert set(d) == {"name", "description", "input_schema"}
            assert d["description"].strip() and d["input_schema"]["type"] == "object"
        assert hub.tool_defs({"get_user", "no_such_tool"})[0]["name"] == "get_user"
        assert hub.tool_defs(set()) == []


async def test_successful_call_and_unknown_tool():
    async with McpHub.start(SETTINGS) as hub:
        good = await hub.call("get_user", {"user_id": "u-104"})
        assert good["ok"] is True and good["data"]["name"] == "Dev Patel"
        unknown = await hub.call("drop_database", {})
        assert unknown["error"]["code"] == "NOT_FOUND"


async def test_tools_from_both_servers_work_and_writes_are_reachable_by_code():
    async with McpHub.start(SETTINGS) as hub:
        assert (await hub.call("search_kb", {"query": "vpn authentication failed"}))["ok"]
        assert (
            await hub.call("update_ticket", {"ticket_id": "T-1001", "status": "open", "note": ""})
        )["ok"]


async def test_tool_level_errors_pass_through_without_retry():
    sleeps = Sleeps()
    async with McpHub.start(SETTINGS, sleep=sleeps) as hub:
        result = await hub.call("get_user", {"user_id": "u-999"})
    assert result["error"]["code"] == "NOT_FOUND" and result["error"]["retryable"] is False
    assert sleeps.values == []


async def test_bad_argument_types_are_invalid_input_and_not_retried():
    sleeps = Sleeps()
    async with McpHub.start(SETTINGS, sleep=sleeps) as hub:
        result = await hub.call("search_kb", {"query": "vpn", "limit": "abc"})
    assert result["ok"] is False and result["error"]["code"] == "INVALID_INPUT"
    assert sleeps.values == []


async def test_timeout_once_is_retried_and_succeeds():
    sleeps = Sleeps()
    env = {"FAULT_INJECT": '{"get_user": "TIMEOUT_ONCE"}'}
    async with McpHub.start(SETTINGS, env, sleep=sleeps) as hub:
        result = await hub.call("get_user", {"user_id": "u-101"})
    assert result["ok"] is True
    assert sleeps.values == [0.5]


async def test_persistent_timeout_returns_the_error_after_two_retries():
    sleeps = Sleeps()
    env = {"FAULT_INJECT": '{"get_user": "TIMEOUT"}'}
    async with McpHub.start(SETTINGS, env, sleep=sleeps) as hub:
        result = await hub.call("get_user", {"user_id": "u-101"})
    assert result["error"]["code"] == "TIMEOUT" and result["error"]["retryable"] is True
    assert sleeps.values == [0.5, 1.0]


async def test_non_retryable_fault_is_not_retried():
    sleeps = Sleeps()
    env = {"FAULT_INJECT": '{"get_user": "NOT_FOUND"}'}
    async with McpHub.start(SETTINGS, env, sleep=sleeps) as hub:
        result = await hub.call("get_user", {"user_id": "u-101"})
    assert result["error"]["code"] == "NOT_FOUND" and sleeps.values == []


async def test_fault_inject_from_settings_reaches_the_servers():
    settings = Settings.from_env({"FAULT_INJECT": '{"search_kb": "INTERNAL"}'})
    async with McpHub.start(settings, sleep=Sleeps()) as hub:
        assert (await hub.call("search_kb", {"query": "vpn"}))["error"]["code"] == "INTERNAL"
        assert (await hub.call("get_user", {"user_id": "u-101"}))["ok"] is True


async def test_parent_environment_is_not_inherited_by_the_servers(monkeypatch):
    """Only variables passed through `env` reach the child processes (the API key never does)."""
    monkeypatch.setenv("FAULT_INJECT", '{"get_user": "TIMEOUT"}')
    async with McpHub.start(SETTINGS, sleep=Sleeps()) as hub:
        assert (await hub.call("get_user", {"user_id": "u-101"}))["ok"] is True


async def test_parallel_calls_on_one_hub():
    async with McpHub.start(SETTINGS) as hub:
        results = await asyncio.gather(
            hub.call("get_user", {"user_id": "u-101"}),
            hub.call("find_resource", {"query": "the finance share"}),
            hub.call("search_kb", {"query": "wifi drops"}),
        )
    assert [r["ok"] for r in results] == [True, True, True]
    assert results[1]["data"]["resources"][0]["id"] == "r-05"


async def test_a_server_that_cannot_start_gives_a_helpful_error():
    with pytest.raises(HubError, match="did not start"):
        async with McpHub.start(SETTINGS, servers={"broken": "mcp_servers/does_not_exist.py"}):
            pass


async def test_errors_raised_inside_the_block_are_not_wrapped_in_exception_groups():
    with pytest.raises(ZeroDivisionError):
        async with McpHub.start(SETTINGS):
            raise ZeroDivisionError("boom")


# ---------- registry and envelope handling (no processes) ----------


def tool(name: str):
    return SimpleNamespace(name=name, description="d", inputSchema={"type": "object"})


def test_registry_builder_merges_servers():
    registry = build_registry([("a", "sess-a", [tool("x")]), ("b", "sess-b", [tool("y")])])
    assert set(registry) == {"x", "y"} and registry["y"][0] == "sess-b"


def test_registry_builder_rejects_duplicate_names():
    with pytest.raises(HubError, match="duplicate tool name 'x'"):
        build_registry([("a", None, [tool("x")]), ("b", None, [tool("x")])])


def result(text="", is_error=False):
    content = [SimpleNamespace(text=text)] if text is not None else []
    return SimpleNamespace(content=content, isError=is_error)


def test_parse_envelope_accepts_valid_success_and_failure():
    ok_text = '{"ok": true, "data": {"a": 1}}'
    assert _parse_envelope("t", result(ok_text)) == {"ok": True, "data": {"a": 1}}
    bad_text = '{"ok": false, "error": {"code": "X", "message": "m", "retryable": false}}'
    assert _parse_envelope("t", result(bad_text))["error"]["code"] == "X"


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"ok": "yes"}',
        '{"ok": true}',
        '{"ok": false}',
        '{"ok": true, "data": 5}',
        "",
    ],
)
def test_parse_envelope_turns_malformed_output_into_a_retryable_internal_error(text):
    envelope = _parse_envelope("t", result(text))
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "INTERNAL" and envelope["error"]["retryable"] is True


def test_parse_envelope_flags_sdk_errors_as_invalid_input():
    envelope = _parse_envelope("t", result("1 validation error for tArguments", is_error=True))
    assert envelope["error"]["code"] == "INVALID_INPUT" and envelope["error"]["retryable"] is False


class StubSession:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = 0

    async def call_tool(self, name, args):
        self.calls += 1
        outcome = self.behaviour(self.calls)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return await outcome()
        return outcome


def stub_hub(session, sleeps=None, timeout=0.05):
    registry = {"t": (session, tool("t"))}
    return McpHub(registry, sleep=sleeps or Sleeps(), tool_timeout=timeout)


async def test_transport_exception_is_retried_then_reported_as_internal():
    session = StubSession(lambda n: ConnectionResetError("pipe closed"))
    sleeps = Sleeps()
    envelope = await stub_hub(session, sleeps).call("t", {})
    assert envelope["error"]["code"] == "INTERNAL" and envelope["error"]["retryable"] is True
    assert session.calls == 3 and sleeps.values == [0.5, 1.0]
    assert "pipe closed" not in envelope["error"]["message"]  # internals are not echoed


async def test_slow_tool_times_out_and_is_retried():
    async def hang():
        await asyncio.sleep(5)

    session = StubSession(lambda n: hang)
    envelope = await stub_hub(session).call("t", {})
    assert envelope["error"]["code"] == "TIMEOUT" and session.calls == 3


async def test_recovers_when_a_later_attempt_succeeds():
    good = result('{"ok": true, "data": {"v": 1}}')
    session = StubSession(lambda n: ConnectionResetError() if n == 1 else good)
    envelope = await stub_hub(session).call("t", {})
    assert envelope == {"ok": True, "data": {"v": 1}} and session.calls == 2
