"""Opt-in live smoke test for the diagnostics loop (Day 5, milestone 4).

Calls the REAL Anthropic API (costs a few cents). Run from the project root:

    python scripts/smoke_diagnose.py

It triages one hand-written VPN ticket for user u-101: starts both MCP servers, lets the
diagnostics model call the read tools, and prints what it did, the Facts built by code,
and the token usage and cost. It never prints the API key.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.diagnostics import diagnose  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.guardrails import Counters, LimitExceeded  # noqa: E402
from src.llm import AnthropicLLM, LLMError  # noqa: E402
from src.mcp_hub import McpHub  # noqa: E402
from src.schemas import Category, Classification, Severity, Ticket  # noqa: E402

TICKET = Ticket(
    id="SMOKE-001",
    subject="VPN says authentication failed",
    body=(
        "Since this morning my VPN client rejects my password with 'authentication failed'. "
        "I can still sign in to Outlook with the same password. Working from home today."
    ),
    requester_id="u-101",
)

CLASSIFICATION = Classification(
    category=Category.VPN_NETWORK,
    severity=Severity.P3,
    confidence=0.9,
    affected_system="VPN",
    summary="VPN client rejects the requester's credentials.",
)


async def main() -> int:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set. Create .env first (see .env.example).")
        return 2
    llm = AnthropicLLM(settings)
    counters = Counters()
    async with McpHub.start(settings) as hub:
        print(f"MCP tools available: {', '.join(hub.tool_names)}")
        try:
            facts, usage = await diagnose(
                llm, hub, TICKET, CLASSIFICATION, None, settings, counters=counters
            )
        except LimitExceeded as exc:
            print(f"LIMIT HIT: {exc.kind}")
            return 1
        except LLMError as exc:
            print(f"MODEL ERROR: {type(exc).__name__}: {exc}")
            return 1

    print(f"\nModel: {settings.model_diagnostics}")
    print(f"Model calls (loop iterations): {counters.iterations}")
    print(f"Tool calls: {counters.tool_calls}")
    for call in facts.tool_calls:
        status = "ok" if call.ok else f"ERROR {call.error_code}"
        print(f"  - {call.name}({call.args}) -> {status} [{call.ms} ms]")
    who = f"{facts.user.name} ({facts.user.role})" if facts.user else None
    print(f"\nUser: {who}")
    print(f"Access: {facts.access}")
    print(f"KB matches: {[(m.id, m.score) for m in facts.kb_matches]}")
    print(f"Gaps: {facts.gaps or 'none'}")
    print(
        f"\nTokens in/out: {usage.input_tokens}/{usage.output_tokens}  "
        f"cache read/write: {usage.cache_read_tokens}/{usage.cache_write_tokens}"
    )
    print(f"Cost: ${usage.cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
