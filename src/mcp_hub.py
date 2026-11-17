"""The MCP hub: starts both tool servers once and routes tool calls (blueprint B5, ADR-017).

The hub is the only code that talks to the MCP client library. Agents ask it for tool
definitions (what the model may see) and call tools through it. `call` ALWAYS returns an
envelope dict; it never raises for tool-level or transport problems.

Important MCP fact: a child server process does NOT inherit the parent's environment (only a
short safe list such as PATH). Variables a server needs, such as FAULT_INJECT, must be passed
explicitly through the `env` parameter below. The API key is deliberately never passed.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_servers.common import err
from src.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVERS: dict[str, str] = {
    "directory": "mcp_servers/directory_server.py",
    "itsm": "mcp_servers/itsm_server.py",
}

READ_ONLY_TOOLS = frozenset(
    {"get_user", "find_resource", "check_access", "search_kb", "get_ticket"}
)
WRITE_TOOLS = frozenset({"update_ticket", "add_comment"})  # coordinator commit step only

TOOL_TIMEOUT_SECONDS = 10.0
STARTUP_TIMEOUT_SECONDS = 20.0
RETRY_DELAYS = (0.5, 1.0)  # a retryable error is retried twice: after 0.5 s, then after 1 s


class HubError(Exception):
    """The hub could not start (a server failed to start, or two tools share a name)."""


Registry = dict[str, tuple[Any, Any]]  # tool name -> (client session, tool description)


def build_registry(listings: Iterable[tuple[str, Any, Sequence[Any]]]) -> Registry:
    """Merge the tool lists of all servers; a duplicate tool name is a startup error."""
    registry: Registry = {}
    for server, session, tools in listings:
        for tool in tools:
            if tool.name in registry:
                raise HubError(f"duplicate tool name {tool.name!r} (second one is in {server!r})")
            registry[tool.name] = (session, tool)
    return registry


def _unwrap(exc: BaseException) -> BaseException:
    """The MCP client's task groups wrap errors in exception groups. When a group holds exactly
    one error, hand that error to the caller so `except HubError` and friends keep working."""
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


def _parse_envelope(name: str, result: Any) -> dict[str, Any]:
    """Turn a raw MCP tool result into an envelope. Anything odd becomes an error envelope."""
    text = result.content[0].text if result.content else ""
    if result.isError:
        # FastMCP reports bad arguments (wrong type, missing field) this way. Retrying cannot help.
        return err("INVALID_INPUT", f"{name} rejected the arguments: {text[:200]}")
    try:
        envelope = json.loads(text)
    except ValueError:
        return err("INTERNAL", f"{name} returned something that is not JSON", retryable=True)
    if (
        not isinstance(envelope, dict)
        or not isinstance(envelope.get("ok"), bool)
        or (envelope["ok"] and not isinstance(envelope.get("data"), dict))
        or (not envelope["ok"] and not isinstance(envelope.get("error"), dict))
    ):
        return err("INTERNAL", f"{name} returned an unexpected shape", retryable=True)
    return envelope


class McpHub:
    def __init__(
        self,
        registry: Registry,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        tool_timeout: float = TOOL_TIMEOUT_SECONDS,
    ) -> None:
        self._registry = registry
        self._sleep = sleep
        self.tool_timeout = tool_timeout

    @classmethod
    @asynccontextmanager
    async def start(
        cls,
        settings: Settings,
        env: dict[str, str] | None = None,
        *,
        servers: dict[str, str] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> AsyncIterator[McpHub]:
        """Start every server, then yield the hub. Servers stop when the block ends.

        Use it as `async with McpHub.start(settings) as hub:` in ONE task (do not enter it in a
        pytest fixture): the MCP client uses task groups that must exit where they were entered.
        """
        child_env = dict(env or {})
        if settings.fault_inject and "FAULT_INJECT" not in child_env:
            child_env["FAULT_INJECT"] = settings.fault_inject
        try:
            async with AsyncExitStack() as stack:
                listings: list[tuple[str, Any, Sequence[Any]]] = []
                for server, relative_path in (servers or SERVERS).items():
                    params = StdioServerParameters(
                        command=sys.executable,
                        args=[str(REPO_ROOT / relative_path)],
                        env=child_env or None,
                    )
                    try:
                        read, write = await stack.enter_async_context(stdio_client(params))
                        session = await stack.enter_async_context(ClientSession(read, write))
                        await asyncio.wait_for(session.initialize(), STARTUP_TIMEOUT_SECONDS)
                        tools = (await session.list_tools()).tools
                    except Exception as exc:  # noqa: BLE001 - re-raised with a helpful message
                        raise HubError(
                            f"MCP server {server!r} did not start ({type(exc).__name__}). "
                            f"Run `python {relative_path}` alone and read its stderr."
                        ) from exc
                    listings.append((server, session, tools))
                yield cls(build_registry(listings), sleep=sleep)
        except BaseExceptionGroup as group:
            raise _unwrap(group) from None

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._registry)

    def tool_defs(self, allowed: Iterable[str]) -> list[dict[str, Any]]:
        """Tool definitions in the shape the Messages API expects, sorted by name so the
        prompt prefix is identical on every call (good for prompt caching)."""
        allowed_set = set(allowed)
        return [
            {
                "name": name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
            for name, (_, tool) in sorted(self._registry.items())
            if name in allowed_set
        ]

    async def _call_once(self, session: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await asyncio.wait_for(session.call_tool(name, args), self.tool_timeout)
        except TimeoutError:
            return err("TIMEOUT", f"{name} did not answer within {self.tool_timeout:g} s", True)
        except Exception as exc:  # noqa: BLE001 - transport failure becomes an envelope
            return err("INTERNAL", f"{name} transport failure ({type(exc).__name__})", True)
        return _parse_envelope(name, result)

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Run one tool and return its envelope. Retryable errors are retried twice."""
        entry = self._registry.get(name)
        if entry is None:
            return err("NOT_FOUND", f"Unknown tool {name!r}")
        session = entry[0]
        envelope = await self._call_once(session, name, args)
        for delay in RETRY_DELAYS:
            if envelope["ok"] or not envelope["error"].get("retryable", False):
                break
            await self._sleep(delay)
            envelope = await self._call_once(session, name, args)
        return envelope
