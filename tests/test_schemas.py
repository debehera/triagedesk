"""Contract tests for src/schemas.py (PRD: FR-2, FR-10, FR-44, FR-50, FR-51)."""

import json

import pytest
from pydantic import ValidationError

from src.schemas import (
    Category,
    Classification,
    Outcome,
    Resolution,
    RiskFlag,
    Severity,
    Ticket,
    TriageResult,
    Usage,
)

VALID_CLASSIFICATION = {
    "category": "vpn_network",
    "severity": "P3",
    "confidence": 0.9,
    "affected_system": "VPN",
    "summary": "VPN login fails",
    "risk_flags": ["multi_issue"],
}


def make_ticket(**overrides) -> dict:
    data = {"id": "T1", "subject": "VPN down", "body": "cannot connect", "requester_id": "u-101"}
    data.update(overrides)
    return data


def test_valid_ticket():
    assert Ticket(**make_ticket()).id == "T1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject": "   "},
        {"body": "   "},
        {"id": ""},
        {"id": "x" * 65},
        {"body": "y" * 8001},
        {"subject": "s" * 201},
        {"requester_id": ""},
    ],
)
def test_invalid_ticket_rejected(overrides):
    with pytest.raises(ValidationError):
        Ticket(**make_ticket(**overrides))


def test_ticket_thread_role_validated():
    with pytest.raises(ValidationError):
        Ticket(**make_ticket(thread=[{"role": "robot", "text": "hi"}]))


def test_classification_parses_enums():
    c = Classification.model_validate_json(json.dumps(VALID_CLASSIFICATION))
    assert c.category is Category.VPN_NETWORK
    assert c.severity.level == 3
    assert c.risk_flags == [RiskFlag.MULTI_ISSUE]


@pytest.mark.parametrize(
    "overrides",
    [{"category": "nonsense"}, {"confidence": 1.4}, {"confidence": -0.1}, {"severity": "P9"}],
)
def test_classification_rejects_bad_values(overrides):
    with pytest.raises(ValidationError):
        Classification(**{**VALID_CLASSIFICATION, **overrides})


def test_security_terms_flag_exists_and_is_in_tool_schema():
    """CR-2: the code-detected flag is part of the contract."""
    assert RiskFlag.SECURITY_TERMS.value == "security_terms"
    schema = json.dumps(Classification.model_json_schema())
    assert "security_terms" in schema


def test_outcome_rank_orders_by_caution():
    assert Outcome.AUTO_RESOLVED.rank < Outcome.PENDING_APPROVAL.rank < Outcome.ESCALATED.rank


def test_severity_levels():
    assert [s.level for s in (Severity.P1, Severity.P2, Severity.P3, Severity.P4)] == [1, 2, 3, 4]


def test_usage_addition():
    total = Usage(input_tokens=1, cost_usd=0.5) + Usage(input_tokens=2, output_tokens=3)
    assert (total.input_tokens, total.output_tokens, total.cost_usd) == (3, 3, 0.5)


def test_resolution_confidence_bounds():
    with pytest.raises(ValidationError):
        Resolution(proposed_outcome="ESCALATED", confidence=2)


def test_result_round_trip_and_explainability_fields():
    """US-4: a result carries everything needed to explain an outcome."""
    result = TriageResult(ticket_id="T1", final_outcome="ESCALATED")
    data = json.loads(result.model_dump_json())
    assert data["final_outcome"] == "ESCALATED"
    for field in ("classification", "facts", "reasons", "guardrail_hits", "usage", "trace"):
        assert field in data
