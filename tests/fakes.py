"""Test doubles for the agent loops: a scripted model and a scripted tool hub.

FakeLLM pops one prepared response per `create` call and records every call it receives (deep
copies, so later changes to the message list do not rewrite history). FakeHub answers tool calls
from prepared envelopes and logs them. Neither touches the network or starts a process.
"""

from __future__ import annotations

import copy
import itertools
from typing import Any

from mcp_servers.common import err, ok
from src.llm import LLMResponse, ToolUse
from src.mcp_hub import READ_ONLY_TOOLS, WRITE_TOOLS
from src.schemas import Usage

_ids = itertools.count(1)


def usage(input_tokens: int = 100, output_tokens: int = 20) -> Usage:
    return Usage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=0.001)


def text_response(text: str = "DONE", *, stop_reason: str = "end_turn") -> LLMResponse:
    return LLMResponse(
        stop_reason=stop_reason,
        text=text,
        tool_uses=[],
        content=[{"type": "text", "text": text}] if text else [],
        usage=usage(),
    )


def tool_use_response(calls: list[tuple[str, dict[str, Any]]], *, text: str = "") -> LLMResponse:
    """A model turn that asks for several tools at once (stop_reason "tool_use")."""
    tool_uses = [ToolUse(id=f"toolu_{next(_ids)}", name=n, input=a) for n, a in calls]
    content: list[dict[str, Any]] = [{"type": "text", "text": text}] if text else []
    content += [
        {"type": "tool_use", "id": t.id, "name": t.name, "input": t.input} for t in tool_uses
    ]
    return LLMResponse(
        stop_reason="tool_use", text=text, tool_uses=tool_uses, content=content, usage=usage()
    )


class FakeLLM:
    def __init__(self, script: list[LLMResponse | Exception]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(copy.deepcopy(kwargs))
        if not self.script:
            raise AssertionError(
                "FakeLLM script exhausted: the code called the model once too often"
            )
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# ---------- canned tool answers ----------


def user_ok(user_id: str = "u-104", **overrides: Any) -> dict[str, Any]:
    data = {
        "id": user_id,
        "name": "Dev Patel",
        "department": "Finance",
        "role": "Financial Analyst",
        "manager_id": "u-110",
        "status": "active",
    }
    return ok({**data, **overrides})


def access_ok(
    resource_id: str = "r-05", sensitivity: str = "restricted", **overrides: Any
) -> dict[str, Any]:
    data = {
        "user_id": "u-104",
        "resource_id": resource_id,
        "resource_name": "Finance Shared Drive",
        "sensitivity": sensitivity,
        "has_access": False,
        "eligible": True,
    }
    return ok({**data, **overrides})


def kb_ok(*matches: tuple[str, float]) -> dict[str, Any]:
    return ok(
        {
            "matches": [
                {
                    "id": article_id,
                    "title": f"Article {article_id}",
                    "category": "vpn_network",
                    "score": score,
                    "steps": ["Step one", "Step two", "Step three"],
                }
                for article_id, score in matches
            ]
        }
    )


def resource_ok() -> dict[str, Any]:
    return ok(
        {"resources": [{"id": "r-05", "name": "Finance Shared Drive", "sensitivity": "restricted"}]}
    )


def error_envelope(code: str, retryable: bool = False) -> dict[str, Any]:
    return err(code, f"{code} (fake)", retryable)


class FakeHub:
    """Same interface as McpHub: tool_defs(allowed) and call(name, args)."""

    def __init__(self, responses: dict[str, dict[str, Any] | list[dict[str, Any]]]) -> None:
        self.responses = {k: (list(v) if isinstance(v, list) else v) for k, v in responses.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tool_defs(self, allowed) -> list[dict[str, Any]]:
        known = sorted(READ_ONLY_TOOLS | WRITE_TOOLS)
        return [
            {"name": n, "description": f"fake {n}", "input_schema": {"type": "object"}}
            for n in known
            if n in set(allowed)
        ]

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, copy.deepcopy(args)))
        if name not in self.responses:
            return err("NOT_FOUND", f"Unknown tool {name!r}")
        answer = self.responses[name]
        if isinstance(answer, list):
            return answer.pop(0) if len(answer) > 1 else answer[0]
        return answer
