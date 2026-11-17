"""Deterministic guardrails (CLAUDE.md rule 1). SKELETON: completed on Day 7.

Today it only provides the pieces the diagnostics loop needs: the two exceptions, the
`Counters` record and an allow-list-only `pre_tool_check`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.schemas import Facts, Ticket, Usage


class LimitExceeded(Exception):
    """A budget was exhausted. `kind` is one of: iterations, tool_calls, tokens (guardrail G5).

    `usage` and `partial_facts` carry what had been spent and gathered before the limit hit,
    so the coordinator can still report the cost and the facts of an escalated ticket.
    """

    def __init__(
        self, kind: str, *, usage: Usage | None = None, partial_facts: Facts | None = None
    ) -> None:
        if kind not in {"iterations", "tool_calls", "tokens"}:
            raise ValueError(f"unknown limit kind {kind!r}")
        super().__init__(f"limit exceeded: {kind}")
        self.kind = kind
        self.usage = usage
        self.partial_facts = partial_facts


class GuardrailBlocked(Exception):
    """The pre-tool check refused a tool call proposed by the model."""


@dataclass
class Counters:
    iterations: int = 0
    tool_calls: int = 0
    est_input_tokens: int = 0


def pre_tool_check(name: str, args: dict[str, Any], *, ticket: Ticket, allowed: set[str]) -> None:
    """Stub: only the allow-list. Day 7 adds argument checks (requester id, formats, lengths)."""
    if name not in allowed:
        raise GuardrailBlocked(f"tool {name!r} is not allowed for this step")
