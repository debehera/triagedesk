"""Opt-in live smoke test for the diagnostics loop (Day 5, milestone 4).

Calls the REAL Anthropic API (costs a few cents). Run from the project root:

    python scripts/smoke_diagnose.py            # the built-in VPN ticket
    python scripts/smoke_diagnose.py EV-024     # an eval ticket (hand-made classification)

With an eval id, the classification comes from the ticket's expected labels (this script does
not run the classifier), and security or P1 tickets get only the get_user tool (least privilege).
Without one it triages one hand-written VPN ticket for user u-101: starts both MCP servers, lets the
diagnostics model call the read tools, and prints what it did, the Facts built by code,
and the token usage and cost. It never prints the API key.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.diagnostics import diagnose  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.guardrails import Counters, LimitExceeded, apply_guardrails  # noqa: E402
from src.llm import AnthropicLLM, LLMError  # noqa: E402
from src.mcp_hub import READ_ONLY_TOOLS, McpHub  # noqa: E402
from src.schemas import Category, Classification, Outcome, Resolution, Severity, Ticket  # noqa: E402

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


def load_eval_ticket(ticket_id: str) -> tuple[Ticket, Classification, set[str]]:
    """An eval ticket, a classification built from its labels and the tools it may use."""
    path = Path(__file__).resolve().parent.parent / "evals" / "tickets.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["id"] != ticket_id:
            continue
        if item["split"] == "holdout":
            raise SystemExit(f"{ticket_id} is in the holdout split; not before Day 13.")
        expected = item["expected"]
        ticket = Ticket.model_validate(
            {k: item[k] for k in ("id", "subject", "body", "requester_id")}
        )
        classification = Classification(
            category=Category(expected["category"]),
            severity=Severity(expected["severity"]),
            confidence=0.9,
            affected_system="(hand-made for the smoke test)",
            summary=item["subject"][:300],
        )
        restricted = classification.category is Category.SECURITY_INCIDENT or (
            classification.severity is Severity.P1
        )
        return ticket, classification, ({"get_user"} if restricted else set(READ_ONLY_TOOLS))
    raise SystemExit(f"No eval ticket {ticket_id}.")


async def main(ticket_id: str | None = None) -> int:
    ticket, classification, allowed = TICKET, CLASSIFICATION, set(READ_ONLY_TOOLS)
    if ticket_id:
        ticket, classification, allowed = load_eval_ticket(ticket_id)
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set. Create .env first (see .env.example).")
        return 2
    llm = AnthropicLLM(settings)
    counters = Counters()
    async with McpHub.start(settings) as hub:
        print(f"MCP tools available: {', '.join(hub.tool_names)}")
        print(
            f"Ticket {ticket.id}: {classification.category.value}/{classification.severity.value}"
        )
        print(f"Tools offered to the model: {', '.join(sorted(allowed))}")
        blocked: list[str] = []
        try:
            facts, usage = await diagnose(
                llm,
                hub,
                ticket,
                classification,
                None,
                settings,
                allowed_tools=allowed,
                counters=counters,
                blocked=blocked,
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
    print(f"Blocked by pre_tool_check: {blocked or 'none'}")
    print(
        f"\nTokens in/out: {usage.input_tokens}/{usage.output_tokens}  "
        f"cache read/write: {usage.cache_read_tokens}/{usage.cache_write_tokens}"
    )
    print(f"Cost: ${usage.cost_usd:.4f}")

    # What the guardrails would do with these REAL facts if a resolver proposed AUTO_RESOLVED.
    pretend = Resolution(
        proposed_outcome=Outcome.AUTO_RESOLVED,
        requester_steps=["(smoke test: no resolver ran)"],
        kb_article_id=facts.kb_matches[0].id if facts.kb_matches else None,
        confidence=0.9,
    )
    decision = apply_guardrails(
        classification=classification,
        facts=facts,
        resolution=pretend,
        counters=counters,
        settings=settings,
    )
    print("\nGuardrailDecision if a resolver had proposed AUTO_RESOLVED:")
    print(decision.model_dump_json(indent=2, exclude={"sanitized_resolution"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
