"""Diagnostics agent: lets the model gather facts with read-only tools (blueprint Day 5, B7).

The loop is explicit about every `stop_reason`, caps iterations and tool calls, runs the tools
of one model turn in parallel, and sends all their results back in ONE user message (an API
rule). The `Facts` are assembled from tool results by `build_facts`, never from model text
(ADR-015), so a hallucinating model cannot invent a user, a KB article or an access record.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from mcp_servers.common import err
from src.config import Settings
from src.guardrails import Counters, GuardrailBlocked, LimitExceeded, pre_tool_check
from src.llm import LLMClient, ToolUse
from src.mcp_hub import READ_ONLY_TOOLS, McpHub
from src.prompts.diagnostics import DIAGNOSTICS_SYSTEM, diagnostics_user_message
from src.schemas import (
    AccessCheck,
    Category,
    Classification,
    Facts,
    KBMatch,
    Severity,
    Ticket,
    ToolCallRecord,
    Usage,
    UserRecord,
)

_SENSITIVITY_RANK = {"standard": 0, "restricted": 1, "privileged": 2}


@dataclass
class ToolOutcome:
    """One executed (or blocked) tool call with its full envelope."""

    name: str
    args: dict[str, Any]
    envelope: dict[str, Any]
    ms: int = 0


# ---------- facts assembly (pure, unit-tested) ----------


def required_tools(classification: Classification, allowed: Collection[str]) -> set[str]:
    """Tools whose results the guardrails depend on (rule G7), limited to the allowed ones."""
    if (
        classification.category is Category.SECURITY_INCIDENT
        or classification.severity is Severity.P1
    ):
        needed = {"get_user"}
    elif classification.category is Category.ACCESS_REQUEST:
        needed = {"get_user", "check_access"}
    else:
        needed = {"get_user", "search_kb"}
    return needed & set(allowed)


def _error_code(outcome: ToolOutcome) -> str:
    return str(outcome.envelope.get("error", {}).get("code", "UNKNOWN"))


def build_facts(
    outcomes: list[ToolOutcome], classification: Classification, allowed: Collection[str]
) -> Facts:
    """Turn tool outcomes into the Facts bundle.

    * get_user -> user (first valid result); check_access -> access (the MOST sensitive result if
      the model checked several resources, so guardrail G2 sees the riskiest one);
      search_kb -> kb_matches (merged over calls, best score per article).
    * find_resource and get_ticket results stay in the trace only.
    * Gaps: a required tool (see `required_tools`) with no successful call gets
      `required:<tool>:<last error code or not_called>`; other failures get `<tool>:<code>`.
    """
    user: UserRecord | None = None
    access: AccessCheck | None = None
    kb: dict[str, KBMatch] = {}
    succeeded: set[str] = set()
    gaps: list[str] = []
    last_error: dict[str, str] = {}
    required = required_tools(classification, allowed)

    for outcome in outcomes:
        envelope = outcome.envelope
        if not envelope["ok"]:
            last_error[outcome.name] = _error_code(outcome)
            continue
        data = envelope["data"]
        try:
            if outcome.name == "get_user":
                user = user or UserRecord.model_validate(data)
            elif outcome.name == "check_access":
                found = AccessCheck.model_validate(data)
                if access is None or (
                    _SENSITIVITY_RANK[found.sensitivity.value]
                    > _SENSITIVITY_RANK[access.sensitivity.value]
                ):
                    access = found
            elif outcome.name == "search_kb":
                for raw in data.get("matches", []):
                    match = KBMatch.model_validate(raw)
                    if match.id not in kb or match.score > kb[match.id].score:
                        kb[match.id] = match
        except ValidationError:
            last_error[outcome.name] = "INVALID_DATA"
            continue
        succeeded.add(outcome.name)

    for name in sorted(required - succeeded):
        gaps.append(f"required:{name}:{last_error.get(name, 'not_called')}")
    for name, code in last_error.items():
        if name not in required and name not in succeeded:
            gaps.append(f"{name}:{code}")

    return Facts(
        user=user,
        access=access,
        kb_matches=sorted(kb.values(), key=lambda m: (-m.score, m.id)),
        gaps=gaps,
        tool_calls=[
            ToolCallRecord(
                name=o.name,
                args=o.args,
                ok=o.envelope["ok"],
                error_code=None if o.envelope["ok"] else _error_code(o),
                retryable=None if o.envelope["ok"] else o.envelope["error"].get("retryable"),
                ms=o.ms,
            )
            for o in outcomes
        ],
    )


# ---------- the agent loop ----------


async def diagnose(
    llm: LLMClient,
    hub: McpHub,
    ticket: Ticket,
    classification: Classification,
    thread_summary: str | None,
    settings: Settings,
    *,
    allowed_tools: Collection[str] = READ_ONLY_TOOLS,
    counters: Counters,
) -> tuple[Facts, Usage]:
    """Run the diagnostics loop. Raises LimitExceeded("iterations" | "tool_calls")."""
    allowed = set(allowed_tools)
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": diagnostics_user_message(ticket, classification, thread_summary),
        }
    ]
    system = [{"type": "text", "text": DIAGNOSTICS_SYSTEM}]
    tools = hub.tool_defs(allowed)
    outcomes: list[ToolOutcome] = []
    usage = Usage()
    stop_notes: list[str] = []

    async def run_one(tool_use: ToolUse) -> ToolOutcome:
        started = time.perf_counter()
        try:
            pre_tool_check(tool_use.name, tool_use.input, ticket=ticket, allowed=allowed)
            envelope = await hub.call(tool_use.name, tool_use.input)
        except GuardrailBlocked as exc:
            envelope = err("FORBIDDEN", str(exc))
        ms = int((time.perf_counter() - started) * 1000)
        return ToolOutcome(tool_use.name, tool_use.input, envelope, ms)

    def limit(kind: str) -> LimitExceeded:
        partial = build_facts(outcomes, classification, allowed)
        return LimitExceeded(kind, usage=usage, partial_facts=partial)

    for iteration in range(settings.max_loop_iterations):
        counters.iterations = iteration + 1
        response = await llm.create(
            role="diagnostics",
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=1024,
        )
        usage += response.usage

        if response.stop_reason == "end_turn":
            break
        if response.stop_reason == "tool_use" and response.tool_uses:
            counters.tool_calls += len(response.tool_uses)
            if counters.tool_calls > settings.max_tool_calls:
                raise limit("tool_calls")
            messages.append({"role": "assistant", "content": response.content})
            results = await asyncio.gather(*(run_one(tu) for tu in response.tool_uses))
            outcomes.extend(results)
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": json.dumps(result.envelope),
                            "is_error": not result.envelope["ok"],
                        }
                        for tu, result in zip(response.tool_uses, results, strict=True)
                    ],
                }
            )
            continue
        # max_tokens, refusal, an empty tool_use turn or anything unexpected: stop, keep the facts
        stop_notes.append(f"diagnostics stopped: {response.stop_reason}")
        break
    else:
        raise limit("iterations")

    facts = build_facts(outcomes, classification, allowed)
    facts.gaps.extend(stop_notes)
    return facts, usage
