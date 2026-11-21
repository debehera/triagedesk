"""Guardrail rules G1-G7 and apply_guardrails (offline, pure code)."""

import itertools

import pytest

from src.config import Settings
from src.guardrails import Counters, GuardrailDecision, apply_guardrails
from src.safety import scan_secrets
from src.schemas import (
    AccessCheck,
    Category,
    Classification,
    Facts,
    KBMatch,
    Outcome,
    Resolution,
    RiskFlag,
    Sensitivity,
    Severity,
    UserRecord,
)

SETTINGS = Settings.from_env({})
AUTO, PENDING, ESC = Outcome.AUTO_RESOLVED, Outcome.PENDING_APPROVAL, Outcome.ESCALATED


def make_classification(
    category=Category.VPN_NETWORK, severity=Severity.P3, confidence=0.9, flags=()
) -> Classification:
    return Classification(
        category=category,
        severity=severity,
        confidence=confidence,
        affected_system="x",
        summary="s",
        risk_flags=list(flags),
    )


def make_access(sensitivity="standard", eligible=True) -> AccessCheck:
    return AccessCheck(
        user_id="u-101",
        resource_id="r-05",
        resource_name="Finance share",
        sensitivity=Sensitivity(sensitivity),
        has_access=False,
        eligible=eligible,
    )


def make_facts(*, access=None, kb=("KB-003",), user="ok", gaps=()) -> Facts:
    record = None
    if user == "ok":
        record = UserRecord(id="u-101", name="Asha Rao", department="Eng", role="Engineer")
    elif user == "disabled":
        record = UserRecord(
            id="u-101", name="A", department="Eng", role="Engineer", status="disabled"
        )
    return Facts(
        user=record,
        access=access,
        kb_matches=[
            KBMatch(id=i, title=i, category=Category.VPN_NETWORK, score=5.0, steps=["s"])
            for i in kb
        ],
        gaps=list(gaps),
    )


def make_resolution(
    outcome=AUTO, confidence=0.9, kb="KB-003", steps=("Restart the VPN client.",), handoff=None
) -> Resolution:
    return Resolution(
        proposed_outcome=outcome,
        requester_steps=list(steps),
        kb_article_id=kb,
        handoff_summary=handoff,
        confidence=confidence,
    )


def decide(*, classification=None, facts=None, resolution="default", limit=None, counters=None):
    return apply_guardrails(
        classification=classification or make_classification(),
        facts=facts or make_facts(),
        resolution=make_resolution() if resolution == "default" else resolution,
        counters=counters or Counters(),
        settings=SETTINGS,
        limit_exceeded=limit,
    )


def rule_ids(decision: GuardrailDecision) -> list[str]:
    return [h.rule_id for h in decision.hits]


# ---------- the clean path ----------


def test_a_clean_auto_resolve_is_left_alone():
    decision = decide()
    assert decision.final_outcome is AUTO and decision.hits == [] and decision.reasons == []
    assert decision.sanitized_resolution is not None


# ---------- G1 ----------


@pytest.mark.parametrize(
    "classification",
    [
        make_classification(Category.SECURITY_INCIDENT),
        make_classification(Category.VPN_NETWORK, Severity.P1),
        make_classification(Category.PASSWORD_RESET, flags=[RiskFlag.SECURITY_TERMS]),
    ],
    ids=["security_category", "p1", "security_terms_flag"],
)
def test_g1_escalates_even_when_the_resolver_says_auto(classification):
    decision = decide(classification=classification, resolution=make_resolution(AUTO))
    assert decision.final_outcome is ESC and "G1" in rule_ids(decision)


def test_model_reported_security_keywords_alone_do_not_trigger_g1():
    decision = decide(classification=make_classification(flags=[RiskFlag.SECURITY_KEYWORDS]))
    assert decision.final_outcome is AUTO


# ---------- G2 ----------


@pytest.mark.parametrize(
    ("sensitivity", "eligible", "expected"),
    [
        ("restricted", True, PENDING),
        ("privileged", True, PENDING),
        ("standard", False, PENDING),
        ("restricted", False, PENDING),
        ("standard", True, AUTO),
    ],
)
def test_g2_access_rules(sensitivity, eligible, expected):
    decision = decide(
        classification=make_classification(Category.ACCESS_REQUEST),
        facts=make_facts(access=make_access(sensitivity, eligible), kb=()),
        resolution=make_resolution(AUTO, kb=None, steps=("Access granted.",)),
    )
    assert decision.final_outcome is expected
    assert ("G2" in rule_ids(decision)) is (expected is PENDING)
    assert "G4" not in rule_ids(decision)  # CR-1: G2 alone handles these


# ---------- G3 ----------


@pytest.mark.parametrize(
    ("classification_conf", "resolution_conf", "expected"),
    [
        (0.65, 0.95, ESC),
        (0.95, 0.60, ESC),
        (0.71, 0.71, AUTO),
        (0.70, 0.70, AUTO),
        (0.6999, 0.9, ESC),
    ],
)
def test_g3_threshold(classification_conf, resolution_conf, expected):
    decision = decide(
        classification=make_classification(confidence=classification_conf),
        resolution=make_resolution(confidence=resolution_conf),
    )
    assert decision.final_outcome is expected


def test_without_a_classification_everything_escalates():
    kwargs = {"facts": make_facts(), "counters": Counters(), "settings": SETTINGS}
    only_start = apply_guardrails(classification=None, resolution=None, **kwargs)
    assert only_start.final_outcome is ESC and only_start.hits == []  # already ESCALATED
    odd = apply_guardrails(classification=None, resolution=make_resolution(AUTO), **kwargs)
    assert odd.final_outcome is ESC and rule_ids(odd) == ["G3"]


# ---------- G4 ----------


@pytest.mark.parametrize(
    ("kb_article_id", "expected"),
    [(None, ESC), ("KB-999", ESC), ("KB-003", AUTO)],
)
def test_g4_needs_a_matched_kb_article(kb_article_id, expected):
    decision = decide(resolution=make_resolution(AUTO, kb=kb_article_id))
    assert decision.final_outcome is expected
    assert ("G4" in rule_ids(decision)) is (expected is ESC)


def test_g4_does_not_apply_to_a_pending_proposal():
    decision = decide(resolution=make_resolution(PENDING, kb=None))
    assert decision.final_outcome is PENDING and decision.hits == []


def test_g4_access_request_without_an_access_check_escalates():
    decision = decide(
        classification=make_classification(Category.ACCESS_REQUEST),
        facts=make_facts(access=None, kb=()),  # user found, no required-gap recorded
        resolution=make_resolution(AUTO, kb=None),
    )
    assert decision.final_outcome is ESC and rule_ids(decision) == ["G4"]


def test_g7_and_g4_both_demand_escalation_but_only_the_first_is_recorded():
    decision = decide(
        classification=make_classification(Category.ACCESS_REQUEST),
        facts=make_facts(access=None, kb=(), gaps=["required:check_access:not_called"]),
        resolution=make_resolution(AUTO, kb=None),
    )
    assert decision.final_outcome is ESC and rule_ids(decision) == ["G7"]  # G4 no longer raises


# ---------- G5 ----------


@pytest.mark.parametrize("kind", ["iterations", "tool_calls", "tokens"])
def test_g5_limit_exceeded(kind):
    decision = decide(limit=kind)
    assert decision.final_outcome is ESC and kind in decision.reasons[0]


@pytest.mark.parametrize(
    "counters",
    [
        Counters(iterations=SETTINGS.max_loop_iterations + 1),
        Counters(tool_calls=SETTINGS.max_tool_calls + 1),
        Counters(est_input_tokens=SETTINGS.max_input_tokens_per_ticket + 1),
    ],
)
def test_g5_also_checks_the_counters_directly(counters):
    assert decide(counters=counters).final_outcome is ESC


def test_counters_exactly_at_the_limit_are_fine():
    at_limit = Counters(
        SETTINGS.max_loop_iterations, SETTINGS.max_tool_calls, SETTINGS.max_input_tokens_per_ticket
    )
    assert decide(counters=at_limit).final_outcome is AUTO


# ---------- G6 ----------


def test_g6_redacts_secrets_in_steps_and_handoff():
    resolution = make_resolution(
        AUTO,
        steps=("Sign in with password: Winter2026! and restart.", "Open the VPN client."),
        handoff="Your new password is Tr0ub4dor&3.",
    )
    decision = decide(resolution=resolution)
    assert decision.final_outcome is ESC and "G6" in rule_ids(decision)
    clean = decision.sanitized_resolution
    assert clean is not None
    assert (
        "[REDACTED]" in clean.requester_steps[0]
        and clean.requester_steps[1] == "Open the VPN client."
    )
    assert "[REDACTED]" in (clean.handoff_summary or "")
    assert all(scan_secrets(t) == [] for t in [*clean.requester_steps, clean.handoff_summary or ""])
    assert "Winter2026" in resolution.requester_steps[0]  # the input is not modified


def test_g6_is_recorded_even_when_the_outcome_is_already_escalated():
    decision = decide(
        classification=make_classification(Category.SECURITY_INCIDENT),
        resolution=make_resolution(ESC, kb=None, handoff="Temp password is hunter2hunter2"),
    )
    g6 = [h for h in decision.hits if h.rule_id == "G6"]
    assert len(g6) == 1 and g6[0].from_outcome is ESC and g6[0].to_outcome is ESC
    assert "hunter2" not in (decision.sanitized_resolution.handoff_summary or "")


def test_clean_resolution_is_returned_unchanged():
    resolution = make_resolution()
    assert decide(resolution=resolution).sanitized_resolution is resolution


# ---------- G7 ----------


@pytest.mark.parametrize(
    "facts",
    [
        make_facts(user=None, gaps=["required:get_user:NOT_FOUND"]),
        make_facts(user=None),
        make_facts(user="disabled"),
        make_facts(gaps=["required:get_user:NOT_FOUND"]),
        make_facts(gaps=["required:search_kb:TIMEOUT"]),
    ],
    ids=["no_user_with_gap", "no_user", "disabled", "required_gap_a", "required_gap_b"],
)
def test_g7_escalates(facts):
    decision = decide(facts=facts)
    assert decision.final_outcome is ESC and "G7" in rule_ids(decision)


def test_a_non_required_gap_alone_does_nothing():
    assert decide(facts=make_facts(gaps=["find_resource:NOT_FOUND"])).final_outcome is AUTO


# ---------- no resolution ----------


def test_without_a_resolution_the_start_is_escalated():
    decision = decide(resolution=None)
    assert decision.final_outcome is ESC and decision.sanitized_resolution is None


# ---------- hits ----------


def test_hits_record_the_chain_of_from_and_to():
    decision = decide(
        classification=make_classification(Category.ACCESS_REQUEST, confidence=0.5),
        facts=make_facts(access=make_access("restricted"), kb=()),
        resolution=make_resolution(AUTO, kb=None),
    )
    assert rule_ids(decision) == ["G2", "G3"]
    first, second = decision.hits
    assert (first.from_outcome, first.to_outcome) == (AUTO, PENDING)
    assert (second.from_outcome, second.to_outcome) == (PENDING, ESC)
    assert decision.final_outcome is ESC and len(decision.reasons) == 2


def test_a_rule_that_does_not_raise_is_not_recorded():
    decision = decide(
        classification=make_classification(Category.SECURITY_INCIDENT, confidence=0.1),
        resolution=make_resolution(ESC, kb=None),
    )
    assert decision.hits == []  # the proposal was already ESCALATED


def test_the_decision_serialises_to_json():
    decision = decide(
        classification=make_classification(Category.ACCESS_REQUEST),
        facts=make_facts(access=make_access("restricted"), kb=()),
        resolution=make_resolution(AUTO, kb=None),
    )
    assert GuardrailDecision.model_validate_json(decision.model_dump_json()) == decision
    assert '"PENDING_APPROVAL"' in decision.model_dump_json()


# ---------- the property: guardrails never relax an outcome ----------


def test_never_less_cautious_over_every_combination():
    checked = 0
    for (
        proposed,
        category,
        severity,
        access_kind,
        eligible,
        c_conf,
        r_conf,
        flag,
        cited,
    ) in itertools.product(
        Outcome,
        Category,
        (Severity.P1, Severity.P3),
        (None, "standard", "restricted", "privileged"),
        (True, False),
        (0.5, 0.7, 0.95),
        (0.5, 0.7, 0.95),
        (False, True),
        (False, True),
    ):
        access = make_access(access_kind, eligible) if access_kind else None
        classification = make_classification(
            category, severity, c_conf, [RiskFlag.SECURITY_TERMS] if flag else []
        )
        resolution = make_resolution(proposed, r_conf, kb="KB-003" if cited else None)
        decision = decide(
            classification=classification,
            facts=make_facts(access=access),
            resolution=resolution,
        )
        final = decision.final_outcome
        context = (proposed, category, severity, access_kind, eligible, c_conf, r_conf, flag, cited)

        assert final.rank >= proposed.rank, context
        if category is Category.SECURITY_INCIDENT or flag or severity is Severity.P1:
            assert final is ESC, context
        if min(c_conf, r_conf) < SETTINGS.confidence_threshold:
            assert final is ESC, context
        if category is Category.ACCESS_REQUEST and access is not None:
            if access_kind in {"restricted", "privileged"} or not eligible:
                assert final.rank >= PENDING.rank, context
        if category is Category.ACCESS_REQUEST and access is None and proposed is AUTO:
            assert final is ESC, context
        if proposed is AUTO and category is not Category.ACCESS_REQUEST and not cited:
            assert final is ESC, context
        checked += 1
    assert checked == 3 * 8 * 2 * 4 * 2 * 3 * 3 * 2 * 2


def test_rule_order_changes_only_the_recorded_hits_not_the_outcome():
    from src import guardrails

    classification = make_classification(Category.ACCESS_REQUEST, confidence=0.5)
    kwargs = {
        "classification": classification,
        "facts": make_facts(access=make_access("restricted"), kb=(), user=None),
        "resolution": make_resolution(AUTO, kb=None),
    }
    forward = decide(**kwargs)
    original = guardrails.RULES
    try:
        guardrails.RULES = tuple(reversed(original))
        backward = decide(**kwargs)
    finally:
        guardrails.RULES = original
    assert forward.final_outcome is backward.final_outcome is ESC
    assert rule_ids(forward) != rule_ids(backward)
