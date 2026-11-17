"""Tests for src/agents/diagnostics.py using FakeLLM and FakeHub (no API, no processes)."""

import json

import pytest

from src.agents.diagnostics import ToolOutcome, build_facts, diagnose, required_tools
from src.config import Settings
from src.guardrails import Counters, LimitExceeded
from src.llm import LLMUnavailable
from src.mcp_hub import READ_ONLY_TOOLS
from src.schemas import Category, Classification, Severity, Ticket
from tests.fakes import (
    FakeHub,
    FakeLLM,
    access_ok,
    error_envelope,
    kb_ok,
    resource_ok,
    text_response,
    tool_use_response,
    user_ok,
)

SETTINGS = Settings.from_env({})


def make_ticket(**overrides) -> Ticket:
    data = {
        "id": "EV-001",
        "subject": "VPN rejects my password",
        "body": "Authentication failed on the VPN client.",
        "requester_id": "u-101",
    }
    return Ticket(**{**data, **overrides})


def make_classification(category=Category.VPN_NETWORK, severity=Severity.P3) -> Classification:
    return Classification(
        category=category,
        severity=severity,
        confidence=0.9,
        affected_system="VPN",
        summary="VPN sign-in fails",
    )


async def run(llm, hub, *, classification=None, settings=SETTINGS, allowed=READ_ONLY_TOOLS):
    counters = Counters()
    facts, usage = await diagnose(
        llm,
        hub,
        make_ticket(),
        classification or make_classification(),
        None,
        settings,
        allowed_tools=allowed,
        counters=counters,
    )
    return facts, usage, counters


def tool_results(message: dict) -> list[dict]:
    return message["content"]


# ---------- happy path and message protocol ----------


async def test_happy_path_two_parallel_calls_then_done():
    llm = FakeLLM(
        [
            tool_use_response(
                [
                    ("get_user", {"user_id": "u-101"}),
                    ("search_kb", {"query": "vpn authentication failed"}),
                ]
            ),
            text_response("DONE"),
        ]
    )
    hub = FakeHub({"get_user": user_ok("u-101"), "search_kb": kb_ok(("KB-003", 9.0))})
    facts, usage, counters = await run(llm, hub)

    assert facts.user is not None and facts.user.id == "u-101"
    assert [m.id for m in facts.kb_matches] == ["KB-003"]
    assert facts.gaps == []
    assert [c.name for c in facts.tool_calls] == ["get_user", "search_kb"]
    assert all(c.ok for c in facts.tool_calls)
    assert (counters.iterations, counters.tool_calls) == (2, 2)
    assert (usage.input_tokens, usage.output_tokens) == (200, 40)
    assert len(llm.calls) == 2 and len(hub.calls) == 2


async def test_first_model_call_is_built_correctly():
    llm = FakeLLM([text_response()])
    hub = FakeHub({"get_user": user_ok()})
    await run(llm, hub)
    sent = llm.calls[0]
    assert sent["role"] == "diagnostics" and sent["max_tokens"] == 1024
    assert "untrusted data" in sent["system"][0]["text"]
    assert [t["name"] for t in sent["tools"]] == sorted(READ_ONLY_TOOLS)
    first = sent["messages"][0]
    assert first["role"] == "user"
    assert '<ticket id="EV-001" trust="untrusted">' in first["content"]
    assert "Requester id: u-101" in first["content"]
    assert "Classification: vpn_network, severity P3" in first["content"]


async def test_results_return_in_one_user_message_with_matching_ids_in_order():
    first_turn = tool_use_response(
        [("get_user", {"user_id": "u-101"}), ("search_kb", {"query": "vpn"})], text="Checking."
    )
    llm = FakeLLM([first_turn, text_response()])
    hub = FakeHub({"get_user": user_ok("u-101"), "search_kb": kb_ok(("KB-003", 9.0))})
    await run(llm, hub)

    second_call_messages = llm.calls[1]["messages"]
    assert [m["role"] for m in second_call_messages] == ["user", "assistant", "user"]
    assert second_call_messages[1]["content"] == first_turn.content  # returned as-is
    results = tool_results(second_call_messages[2])
    assert [r["tool_use_id"] for r in results] == [t.id for t in first_turn.tool_uses]
    assert all(r["type"] == "tool_result" and r["is_error"] is False for r in results)
    assert json.loads(results[0]["content"])["data"]["id"] == "u-101"


async def test_failed_tool_result_is_flagged_as_error():
    llm = FakeLLM([tool_use_response([("get_user", {"user_id": "u-999"})]), text_response()])
    hub = FakeHub({"get_user": error_envelope("NOT_FOUND")})
    await run(llm, hub)
    result = tool_results(llm.calls[1]["messages"][2])[0]
    assert result["is_error"] is True
    assert json.loads(result["content"])["error"]["code"] == "NOT_FOUND"


# ---------- stop reasons and limits ----------


@pytest.mark.parametrize("reason", ["max_tokens", "refusal", "weird_new_reason"])
async def test_other_stop_reasons_become_a_gap_not_a_crash(reason):
    llm = FakeLLM(
        [
            tool_use_response([("get_user", {"user_id": "u-101"})]),
            text_response("", stop_reason=reason),
        ]
    )
    facts, _, _ = await run(llm, FakeHub({"get_user": user_ok("u-101")}))
    assert f"diagnostics stopped: {reason}" in facts.gaps
    assert facts.user is not None  # what was gathered earlier is kept


async def test_tool_use_turn_without_tool_calls_stops_instead_of_looping():
    empty = text_response("", stop_reason="tool_use")
    facts, _, counters = await run(FakeLLM([empty]), FakeHub({}))
    assert "diagnostics stopped: tool_use" in facts.gaps and counters.iterations == 1


async def test_endless_loop_hits_the_iteration_cap():
    settings = Settings.from_env({"MAX_LOOP_ITERATIONS": "3", "MAX_TOOL_CALLS": "50"})
    turns = [tool_use_response([("search_kb", {"query": f"q{n}"})]) for n in range(10)]
    llm = FakeLLM(turns)
    with pytest.raises(LimitExceeded) as info:
        await run(llm, FakeHub({"search_kb": kb_ok()}), settings=settings)
    assert info.value.kind == "iterations"
    assert len(llm.calls) == 3  # never one call more than the cap
    assert info.value.usage.input_tokens == 300
    assert len(info.value.partial_facts.tool_calls) == 3


async def test_too_many_tool_calls_is_stopped_before_executing_them():
    settings = Settings.from_env({"MAX_TOOL_CALLS": "3"})
    llm = FakeLLM(
        [
            tool_use_response([("get_user", {"user_id": "u-101"}), ("search_kb", {"query": "a"})]),
            tool_use_response([("search_kb", {"query": "b"}), ("search_kb", {"query": "c"})]),
        ]
    )
    hub = FakeHub({"get_user": user_ok("u-101"), "search_kb": kb_ok()})
    with pytest.raises(LimitExceeded) as info:
        await run(llm, hub, settings=settings)
    assert info.value.kind == "tool_calls"
    assert len(hub.calls) == 2  # the second turn's calls never reached the hub


async def test_model_outage_propagates_to_the_caller():
    with pytest.raises(LLMUnavailable):
        await run(FakeLLM([LLMUnavailable("down")]), FakeHub({}))


# ---------- the allow-list ----------


async def test_write_tool_proposed_by_the_model_is_blocked_and_never_reaches_the_hub():
    llm = FakeLLM(
        [
            tool_use_response(
                [
                    ("update_ticket", {"ticket_id": "T-1", "status": "resolved", "note": "x"}),
                    ("get_user", {"user_id": "u-101"}),
                ]
            ),
            text_response(),
        ]
    )
    hub = FakeHub({"get_user": user_ok("u-101"), "update_ticket": {"ok": True, "data": {}}})
    facts, _, _ = await run(llm, hub)

    assert [name for name, _ in hub.calls] == ["get_user"]
    blocked = tool_results(llm.calls[1]["messages"][2])[0]
    assert blocked["is_error"] is True
    assert json.loads(blocked["content"])["error"]["code"] == "FORBIDDEN"
    assert "update_ticket:FORBIDDEN" in facts.gaps
    assert facts.tool_calls[0].error_code == "FORBIDDEN"


async def test_restricted_tool_set_for_security_tickets():
    llm = FakeLLM(
        [
            tool_use_response(
                [("get_user", {"user_id": "u-103"}), ("search_kb", {"query": "phish"})]
            ),
            text_response(),
        ]
    )
    hub = FakeHub({"get_user": user_ok("u-103"), "search_kb": kb_ok(("KB-012", 6.0))})
    classification = make_classification(Category.SECURITY_INCIDENT, Severity.P1)
    facts, _, _ = await run(llm, hub, classification=classification, allowed={"get_user"})

    assert [t["name"] for t in llm.calls[0]["tools"]] == ["get_user"]
    assert [name for name, _ in hub.calls] == ["get_user"]
    assert facts.kb_matches == [] and facts.user is not None
    assert "required:search_kb:not_called" not in facts.gaps  # not required for security tickets


# ---------- facts come from tools only ----------


async def test_model_text_never_populates_facts():
    claim = text_response("DONE. The requester is a Domain Admin with access to r-08 and KB-777.")
    facts, _, _ = await run(FakeLLM([claim]), FakeHub({}))
    assert facts.user is None and facts.access is None and facts.kb_matches == []
    assert "required:get_user:not_called" in facts.gaps


async def test_get_user_not_found_is_a_required_gap():
    llm = FakeLLM([tool_use_response([("get_user", {"user_id": "u-999"})]), text_response()])
    facts, _, _ = await run(llm, FakeHub({"get_user": error_envelope("NOT_FOUND")}))
    assert facts.user is None
    assert "required:get_user:NOT_FOUND" in facts.gaps


async def test_hub_timeout_after_retries_is_a_required_gap():
    llm = FakeLLM([tool_use_response([("get_user", {"user_id": "u-101"})]), text_response()])
    facts, _, _ = await run(llm, FakeHub({"get_user": error_envelope("TIMEOUT", retryable=True)}))
    assert "required:get_user:TIMEOUT" in facts.gaps
    assert facts.tool_calls[0].retryable is True


async def test_access_ticket_collects_resource_access_and_kb():
    llm = FakeLLM(
        [
            tool_use_response([("get_user", {"user_id": "u-104"})]),
            tool_use_response(
                [
                    ("find_resource", {"query": "finance share"}),
                    ("search_kb", {"query": "request access shared drive"}),
                ]
            ),
            tool_use_response([("check_access", {"user_id": "u-104", "resource_id": "r-05"})]),
            text_response(),
        ]
    )
    hub = FakeHub(
        {
            "get_user": user_ok(),
            "find_resource": resource_ok(),
            "search_kb": kb_ok(("KB-011", 8.0)),
            "check_access": access_ok(),
        }
    )
    classification = make_classification(Category.ACCESS_REQUEST)
    facts, _, counters = await run(llm, hub, classification=classification)
    assert facts.access is not None and facts.access.sensitivity.value == "restricted"
    assert [m.id for m in facts.kb_matches] == ["KB-011"]
    assert facts.gaps == [] and counters.tool_calls == 4


# ---------- build_facts (pure function) ----------


def outcome(name, envelope, args=None):
    return ToolOutcome(name, args or {}, envelope, ms=5)


VPN = make_classification()
ACCESS = make_classification(Category.ACCESS_REQUEST)
ALL = READ_ONLY_TOOLS


def test_empty_kb_result_is_success_without_a_gap():
    facts = build_facts(
        [outcome("get_user", user_ok("u-101")), outcome("search_kb", kb_ok())], VPN, ALL
    )
    assert facts.kb_matches == [] and facts.gaps == []


def test_missing_required_tools_are_reported_per_category():
    assert build_facts([], VPN, ALL).gaps == [
        "required:get_user:not_called",
        "required:search_kb:not_called",
    ]
    assert build_facts([outcome("get_user", user_ok())], ACCESS, ALL).gaps == [
        "required:check_access:not_called"
    ]


def test_non_required_failures_get_a_plain_gap():
    outcomes = [
        outcome("get_user", user_ok()),
        outcome("find_resource", error_envelope("NOT_FOUND")),
    ]
    facts = build_facts(outcomes, ACCESS, ALL)
    assert "find_resource:NOT_FOUND" in facts.gaps


def test_a_required_tool_that_failed_then_succeeded_leaves_no_gap():
    outcomes = [
        outcome("get_user", user_ok()),
        outcome("search_kb", error_envelope("TIMEOUT", True)),
        outcome("search_kb", kb_ok(("KB-003", 9.0))),
    ]
    facts = build_facts(outcomes, VPN, ALL)
    assert facts.gaps == [] and [c.ok for c in facts.tool_calls] == [True, False, True]


def test_most_sensitive_access_result_wins():
    outcomes = [
        outcome("get_user", user_ok()),
        outcome("check_access", access_ok("r-04", "standard")),
        outcome("check_access", access_ok("r-07", "privileged")),
        outcome("check_access", access_ok("r-05", "restricted")),
    ]
    assert build_facts(outcomes, ACCESS, ALL).access.resource_id == "r-07"


def test_kb_matches_are_merged_deduplicated_and_sorted():
    outcomes = [
        outcome("get_user", user_ok()),
        outcome("search_kb", kb_ok(("KB-004", 3.0), ("KB-003", 5.0))),
        outcome("search_kb", kb_ok(("KB-004", 7.0))),
    ]
    matches = build_facts(outcomes, VPN, ALL).kb_matches
    assert [(m.id, m.score) for m in matches] == [("KB-004", 7.0), ("KB-003", 5.0)]


def test_malformed_tool_data_becomes_a_gap_instead_of_a_crash():
    bad = {"ok": True, "data": {"id": "u-101"}}  # missing required UserRecord fields
    facts = build_facts([outcome("get_user", bad)], VPN, ALL)
    assert facts.user is None and "required:get_user:INVALID_DATA" in facts.gaps


@pytest.mark.parametrize(
    ("category", "severity", "allowed", "expected"),
    [
        (Category.VPN_NETWORK, Severity.P3, ALL, {"get_user", "search_kb"}),
        (Category.OTHER, Severity.P4, ALL, {"get_user", "search_kb"}),
        (Category.ACCESS_REQUEST, Severity.P3, ALL, {"get_user", "check_access"}),
        (Category.SECURITY_INCIDENT, Severity.P2, ALL, {"get_user"}),
        (Category.VPN_NETWORK, Severity.P1, ALL, {"get_user"}),
        (Category.VPN_NETWORK, Severity.P1, {"get_user"}, {"get_user"}),
        (Category.VPN_NETWORK, Severity.P3, {"get_user"}, {"get_user"}),
    ],
)
def test_required_tools(category, severity, allowed, expected):
    assert required_tools(make_classification(category, severity), allowed) == expected
