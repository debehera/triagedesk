"""Canonical data contracts for TriageDesk (src/schemas.py).

Every module imports its types from here. Do not redefine these elsewhere.
Contract changes need an ADR in docs/04-decision-log.md.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Category(StrEnum):
    PASSWORD_RESET = "password_reset"
    ACCESS_REQUEST = "access_request"
    VPN_NETWORK = "vpn_network"
    SOFTWARE_INSTALL = "software_install"
    HARDWARE = "hardware"
    EMAIL_CALENDAR = "email_calendar"
    SECURITY_INCIDENT = "security_incident"
    OTHER = "other"


class Severity(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"

    @property
    def level(self) -> int:
        return int(self.value[1])


class Outcome(StrEnum):
    AUTO_RESOLVED = "AUTO_RESOLVED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ESCALATED = "ESCALATED"

    @property
    def rank(self) -> int:
        """Higher rank = more cautious. Guardrails may only raise the rank."""
        return {"AUTO_RESOLVED": 0, "PENDING_APPROVAL": 1, "ESCALATED": 2}[self.value]


class RiskFlag(StrEnum):
    INJECTION_SUSPECTED = "injection_suspected"
    MULTI_ISSUE = "multi_issue"
    SECURITY_KEYWORDS = "security_keywords"  # model-reported: security-related wording
    PRIVILEGED_RESOURCE = "privileged_resource"
    AMBIGUOUS = "ambiguous"
    SECURITY_TERMS = "security_terms"  # code-detected (detect_security_terms); drives guardrail G1


class Sensitivity(StrEnum):
    STANDARD = "standard"
    RESTRICTED = "restricted"
    PRIVILEGED = "privileged"


# ---------- input ----------


class Message(BaseModel):
    role: Literal["requester", "agent", "it"]
    text: str


class Ticket(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    subject: str = Field(max_length=200)
    body: str = Field(max_length=8000)
    requester_id: str = Field(min_length=1, max_length=64)
    thread: list[Message] = Field(default_factory=list)
    created_at: str | None = None

    @field_validator("subject", "body")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


# ---------- classifier output (also the forced-tool input schema) ----------


class Classification(BaseModel):
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0, description="Your confidence in category+severity")
    affected_system: str = Field(max_length=80, description="e.g. VPN, Outlook, finance share")
    summary: str = Field(max_length=300, description="One-sentence neutral summary of the request")
    risk_flags: list[RiskFlag] = Field(default_factory=list)


# ---------- facts gathered through tools (assembled by CODE, not by the model) ----------


class UserRecord(BaseModel):
    id: str
    name: str
    department: str
    role: str
    manager_id: str | None = None
    status: Literal["active", "disabled"] = "active"


class AccessCheck(BaseModel):
    user_id: str
    resource_id: str
    resource_name: str
    sensitivity: Sensitivity
    has_access: bool
    eligible: bool = Field(description="Role is allowed to request this resource")


class KBMatch(BaseModel):
    id: str
    title: str
    category: Category
    score: float
    steps: list[str]


class ToolCallRecord(BaseModel):
    name: str
    args: dict[str, Any]
    ok: bool
    error_code: str | None = None
    retryable: bool | None = None
    ms: int = 0


class Facts(BaseModel):
    user: UserRecord | None = None
    access: AccessCheck | None = None
    kb_matches: list[KBMatch] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


# ---------- resolver output (also a forced-tool input schema) ----------


class Resolution(BaseModel):
    proposed_outcome: Outcome
    requester_steps: list[str] = Field(default_factory=list, description="Only for AUTO_RESOLVED")
    kb_article_id: str | None = Field(default=None, description="KB article the steps come from")
    handoff_summary: str | None = Field(default=None, description="For escalation / approval")
    confidence: float = Field(ge=0.0, le=1.0)


# ---------- result ----------


class GuardrailHit(BaseModel):
    rule_id: str  # "G1".."G7", "PRE"
    message: str
    from_outcome: Outcome
    to_outcome: Outcome


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


class TraceEvent(BaseModel):
    step: str  # validate | summarize | budget | classify | diagnose | resolve | guardrails | commit
    detail: dict[str, Any] = Field(default_factory=dict)
    ms: int = 0


class TriageResult(BaseModel):
    ticket_id: str
    classification: Classification | None = None
    facts: Facts = Field(default_factory=Facts)
    resolution: Resolution | None = None
    final_outcome: Outcome
    reasons: list[str] = Field(default_factory=list)
    guardrail_hits: list[GuardrailHit] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    latency_ms: int = 0
    trace: list[TraceEvent] = Field(default_factory=list)
