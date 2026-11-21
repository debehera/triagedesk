"""Deterministic guardrails (CLAUDE.md rule 1).

Pure code, no model calls. `pre_tool_check` guards every tool call the model proposes;
`apply_guardrails` (below) decides the final outcome and can only make it more cautious.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from src.config import Settings
from src.safety import redact_secrets, scan_secrets
from src.schemas import (
    Category,
    Classification,
    Facts,
    GuardrailHit,
    Outcome,
    Resolution,
    RiskFlag,
    Severity,
    Ticket,
    Usage,
)


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


# ---------- pre-tool check (least privilege at the tool boundary) ----------

# Re-declared on purpose: src/ must not import server code (mcp_servers/common.py has the same).
USER_ID_RE = re.compile(r"u-[0-9]{3}")
RESOURCE_ID_RE = re.compile(r"r-[0-9]{2}")
TICKET_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")

# The parameters each tool knows. Any other key in the model's arguments is refused.
TOOL_ARGS: dict[str, frozenset[str]] = {
    "get_user": frozenset({"user_id"}),
    "find_resource": frozenset({"query"}),
    "check_access": frozenset({"user_id", "resource_id"}),
    "search_kb": frozenset({"query", "category", "limit"}),
    "get_ticket": frozenset({"ticket_id"}),
    "update_ticket": frozenset({"ticket_id", "status", "note"}),
    "add_comment": frozenset({"ticket_id", "text", "visibility"}),
}
MAX_QUERY = {"find_resource": 100, "search_kb": 200}
_CATEGORIES = frozenset(c.value for c in Category)


def _has_control_chars(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def pre_tool_check(name: str, args: dict[str, Any], *, ticket: Ticket, allowed: set[str]) -> None:
    """Refuse a tool call the model should not make. Raises GuardrailBlocked(reason).

    Checks, in order: the tool is allowed for this step; the argument names are known; the ids
    are well formed; the user id is the REQUESTER of this ticket (diagnostics may look up nobody
    else); free-text and number arguments are sane. Reasons never repeat the argument values.
    """
    if name not in allowed:
        raise GuardrailBlocked(f"tool {name!r} is not allowed for this step")
    known = TOOL_ARGS.get(name)
    if known is None:
        raise GuardrailBlocked(f"tool {name!r} is unknown")
    if not isinstance(args, dict):
        raise GuardrailBlocked("tool arguments must be an object")
    extra = sorted(set(args) - known)
    if extra:
        raise GuardrailBlocked(f"unknown argument(s) for {name}: {', '.join(extra)}")

    if "user_id" in args:
        user_id = args["user_id"]
        if not isinstance(user_id, str) or not USER_ID_RE.fullmatch(user_id):
            raise GuardrailBlocked("user_id is malformed")
        if name in {"get_user", "check_access"} and user_id != ticket.requester_id:
            raise GuardrailBlocked(f"{name} may only look up the requester of this ticket")
    if "resource_id" in args:
        resource_id = args["resource_id"]
        if not isinstance(resource_id, str) or not RESOURCE_ID_RE.fullmatch(resource_id):
            raise GuardrailBlocked("resource_id is malformed")
    if "ticket_id" in args:
        ticket_id = args["ticket_id"]
        if not isinstance(ticket_id, str) or not TICKET_ID_RE.fullmatch(ticket_id):
            raise GuardrailBlocked("ticket_id is malformed")
    if "query" in args:
        query = args["query"]
        limit = MAX_QUERY.get(name, 200)
        if not isinstance(query, str) or not query.strip() or len(query) > limit:
            raise GuardrailBlocked(f"query must be 1-{limit} characters and not blank")
        if _has_control_chars(query):
            raise GuardrailBlocked("query must not contain control characters")
    if "category" in args and args["category"] is not None and args["category"] not in _CATEGORIES:
        raise GuardrailBlocked("category is not a known category")
    if "limit" in args:
        value = args["limit"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise GuardrailBlocked("limit must be an integer from 1 to 5")


# ---------- outcome rules G1-G7 (docs/ARCHITECTURE.md, blueprint B9) ----------


class GuardrailDecision(BaseModel):
    """The guardrail verdict. `final_outcome` is never less cautious than the proposal."""

    final_outcome: Outcome
    hits: list[GuardrailHit] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    sanitized_resolution: Resolution | None = None


@dataclass(frozen=True)
class _Input:
    """Everything a rule may look at (read-only)."""

    classification: Classification | None
    facts: Facts
    resolution: Resolution | None
    counters: Counters
    settings: Settings
    limit_exceeded: str | None


@dataclass(frozen=True)
class _Demand:
    outcome: Outcome
    message: str


Rule = Callable[[_Input], _Demand | None]


def rule_g1(inp: _Input) -> _Demand | None:
    """Security wording or P1 severity always goes to a human."""
    c = inp.classification
    if c is None:
        return None
    if c.category is Category.SECURITY_INCIDENT:
        return _Demand(Outcome.ESCALATED, "G1: security incident")
    if c.severity is Severity.P1:
        return _Demand(Outcome.ESCALATED, "G1: severity P1")
    if RiskFlag.SECURITY_TERMS in c.risk_flags:
        return _Demand(Outcome.ESCALATED, "G1: security terms found in the ticket text")
    return None


def rule_g2(inp: _Input) -> _Demand | None:
    """Restricted, privileged or ineligible access needs approval (CR-1)."""
    c, access = inp.classification, inp.facts.access
    if c is None or c.category is not Category.ACCESS_REQUEST or access is None:
        return None
    if access.sensitivity.value in {"restricted", "privileged"}:
        return _Demand(
            Outcome.PENDING_APPROVAL, f"G2: {access.sensitivity.value} resource needs approval"
        )
    if not access.eligible:
        return _Demand(Outcome.PENDING_APPROVAL, "G2: requester's role is not eligible")
    return None


def rule_g3(inp: _Input) -> _Demand | None:
    """Low confidence from the classifier or the resolver (exactly the threshold passes)."""
    threshold = inp.settings.confidence_threshold
    if inp.classification is None:
        return _Demand(Outcome.ESCALATED, "G3: no classification available")
    confidences = [inp.classification.confidence]
    if inp.resolution is not None:
        confidences.append(inp.resolution.confidence)
    lowest = min(confidences)
    if lowest < threshold:
        return _Demand(
            Outcome.ESCALATED, f"G3: confidence {lowest:.2f} is below the threshold {threshold:.2f}"
        )
    return None


def rule_g4(inp: _Input) -> _Demand | None:
    """No auto-resolve without a cited KB article (or, for access, without an access check)."""
    r, c = inp.resolution, inp.classification
    if r is None or c is None or r.proposed_outcome is not Outcome.AUTO_RESOLVED:
        return None
    if c.category is Category.ACCESS_REQUEST:
        if inp.facts.access is None:
            return _Demand(Outcome.ESCALATED, "G4: no access check result for an access request")
        return None  # restricted, privileged and ineligible are G2's job (CR-1)
    if r.kb_article_id is None or r.kb_article_id not in {m.id for m in inp.facts.kb_matches}:
        return _Demand(Outcome.ESCALATED, "G4: auto-resolve without a matching KB article")
    return None


def rule_g5(inp: _Input) -> _Demand | None:
    """A budget ran out: iterations, tool calls or tokens."""
    if inp.limit_exceeded is not None:
        return _Demand(Outcome.ESCALATED, f"G5: limit exceeded ({inp.limit_exceeded})")
    s, n = inp.settings, inp.counters
    if n.iterations > s.max_loop_iterations:
        return _Demand(Outcome.ESCALATED, "G5: limit exceeded (iterations)")
    if n.tool_calls > s.max_tool_calls:
        return _Demand(Outcome.ESCALATED, "G5: limit exceeded (tool_calls)")
    if n.est_input_tokens > s.max_input_tokens_per_ticket:
        return _Demand(Outcome.ESCALATED, "G5: limit exceeded (tokens)")
    return None


def _resolution_texts(resolution: Resolution) -> list[str]:
    texts = list(resolution.requester_steps)
    if resolution.handoff_summary:
        texts.append(resolution.handoff_summary)
    return texts


def rule_g6(inp: _Input) -> _Demand | None:
    """Secret-like text in what the model wrote (the text itself is redacted separately)."""
    if inp.resolution is None:
        return None
    found: set[str] = set()
    for text in _resolution_texts(inp.resolution):
        found.update(scan_secrets(text))
    if not found:
        return None
    return _Demand(
        Outcome.ESCALATED,
        f"G6: secret-like text redacted from the resolution ({', '.join(sorted(found))})",
    )


def rule_g7(inp: _Input) -> _Demand | None:
    """Missing or disabled requester, or a required tool that never succeeded."""
    user = inp.facts.user
    if user is None:
        return _Demand(Outcome.ESCALATED, "G7: requester not found")
    if user.status == "disabled":
        return _Demand(Outcome.ESCALATED, "G7: requester account is disabled")
    missing = [g for g in inp.facts.gaps if g.startswith("required:")]
    if missing:
        return _Demand(Outcome.ESCALATED, f"G7: required information missing ({missing[0]})")
    return None


# Order only affects the order of the recorded hits, never the final outcome.
RULES: tuple[tuple[str, Rule], ...] = (
    ("G7", rule_g7),
    ("G1", rule_g1),
    ("G5", rule_g5),
    ("G2", rule_g2),
    ("G3", rule_g3),
    ("G4", rule_g4),
    ("G6", rule_g6),
)


def sanitize_resolution(resolution: Resolution) -> Resolution:
    """A copy of the resolution with every secret-like match replaced by [REDACTED]."""
    return resolution.model_copy(
        update={
            "requester_steps": [redact_secrets(step) for step in resolution.requester_steps],
            "handoff_summary": (
                redact_secrets(resolution.handoff_summary) if resolution.handoff_summary else None
            ),
        }
    )


def apply_guardrails(
    *,
    classification: Classification | None,
    facts: Facts,
    resolution: Resolution | None,
    counters: Counters,
    settings: Settings,
    limit_exceeded: str | None = None,
) -> GuardrailDecision:
    """Decide the final outcome. Starts from the proposal and can only raise it.

    With no resolution the start is ESCALATED. Each rule that demands a stricter outcome is
    recorded as a hit. G6 is also recorded when the outcome is already ESCALATED, so the audit
    shows that redaction happened (that hit has from_outcome == to_outcome).
    """
    inp = _Input(classification, facts, resolution, counters, settings, limit_exceeded)
    start = resolution.proposed_outcome if resolution else Outcome.ESCALATED
    current = start
    hits: list[GuardrailHit] = []

    for rule_id, rule in RULES:
        demand = rule(inp)
        if demand is None:
            continue
        raises = demand.outcome.rank > current.rank
        if raises or rule_id == "G6":
            hits.append(
                GuardrailHit(
                    rule_id=rule_id,
                    message=demand.message,
                    from_outcome=current,
                    to_outcome=demand.outcome if raises else current,
                )
            )
        if raises:
            current = demand.outcome

    sanitized = resolution
    if resolution is not None and any(h.rule_id == "G6" for h in hits):
        sanitized = sanitize_resolution(resolution)

    assert current.rank >= start.rank  # the invariant: guardrails never relax an outcome
    return GuardrailDecision(
        final_outcome=current,
        hits=hits,
        reasons=[h.message for h in hits],
        sanitized_resolution=sanitized,
    )
