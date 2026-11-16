"""Pure-logic tests for the ITSM tools (no MCP involved)."""

import json

import pytest

from mcp_servers.itsm_logic import (
    MAX_TICKETS,
    add_comment,
    get_comments,
    get_ticket,
    reset_state,
    search_kb,
    update_ticket,
)
from src.data import load_kb, load_tickets_seed
from src.schemas import KBMatch


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_state()
    yield
    reset_state()


def error_code(result: dict) -> str:
    assert result["ok"] is False
    return result["error"]["code"]


def top_ids(query: str, **kwargs) -> list[str]:
    result = search_kb(query, **kwargs)
    assert result["ok"] is True, result
    return [m["id"] for m in result["data"]["matches"]]


# ---------- seed data ----------


def test_seed_tickets_are_well_formed():
    seeds = load_tickets_seed()
    assert [t.id for t in seeds] == [f"T-{n}" for n in range(1001, 1007)]
    assert {t.status for t in seeds} == {"open", "resolved", "escalated", "pending_approval"}


# ---------- search_kb: retrieval quality ----------


@pytest.mark.parametrize("article", load_kb(), ids=lambda a: a.id)
def test_every_article_is_found_by_its_own_title(article):
    assert top_ids(article.title)[0] == article.id


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("vpn authentication failed", "KB-003"),
        ("cannot reach intranet over vpn", "KB-004"),
        ("wifi drops", "KB-005"),
        ("forgot my password", "KB-001"),
        ("account locked after too many attempts", "KB-002"),
        ("install software", "KB-006"),
        ("outlook not syncing", "KB-007"),
        ("laptop wont charge", "KB-009"),
        ("printer offline", "KB-010"),
        ("need access to shared drive", "KB-011"),
        ("phishing email", "KB-012"),
    ],
)
def test_symptom_queries_rank_the_right_article_first(query, expected):
    assert top_ids(query)[0] == expected


def test_no_match_is_success_with_empty_list():
    result = search_kb("flux capacitor calibration")
    assert result == {"ok": True, "data": {"matches": []}}


def test_match_shape_validates_as_kbmatch():
    match = search_kb("vpn authentication failed")["data"]["matches"][0]
    assert set(match) == {"id", "title", "category", "score", "steps"}
    KBMatch.model_validate(match)
    assert 3 <= len(match["steps"]) <= 5


def test_results_are_sorted_and_limited():
    matches = search_kb("vpn", limit=2)["data"]["matches"]
    assert len(matches) == 2
    assert matches[0]["score"] >= matches[1]["score"]
    assert len(search_kb("vpn", limit=5)["data"]["matches"]) <= 5


def test_search_is_deterministic():
    assert search_kb("network drops") == search_kb("network drops")


def test_category_filter_boosts_the_matching_article():
    plain = {m["id"]: m for m in search_kb("network", limit=5)["data"]["matches"]}
    boosted = {
        m["id"]: m for m in search_kb("network", category="vpn_network", limit=5)["data"]["matches"]
    }
    assert plain.keys() == boosted.keys()  # the filter never adds or removes articles
    for article_id, match in boosted.items():
        extra = 1.5 if match["category"] == "vpn_network" else 0.0
        assert match["score"] == plain[article_id]["score"] + extra


def test_category_alone_never_creates_a_match():
    assert top_ids("flux capacitor", category="hardware") == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 201},
        {"query": None},
        {"query": "vpn", "category": "nonsense"},
        {"query": "vpn", "limit": 0},
        {"query": "vpn", "limit": 9},
        {"query": "vpn", "limit": True},
        {"query": "vpn", "limit": "3"},
    ],
)
def test_search_kb_invalid_input(kwargs):
    assert error_code(search_kb(**kwargs)) == "INVALID_INPUT"


# ---------- get_ticket ----------


def test_get_ticket_returns_seed():
    data = get_ticket("T-1002")["data"]
    assert data["status"] == "resolved"
    assert set(data) == {"id", "subject", "status", "notes"}


def test_get_ticket_unknown_and_malformed():
    assert error_code(get_ticket("T-9999")) == "NOT_FOUND"
    for bad in ["", " ", "a b", "x" * 65, "../etc", None]:
        assert error_code(get_ticket(bad)) == "INVALID_INPUT"


def test_get_ticket_returns_a_copy():
    get_ticket("T-1002")["data"]["notes"].append("tamper")
    assert "tamper" not in get_ticket("T-1002")["data"]["notes"]


# ---------- update_ticket ----------


def test_update_existing_ticket():
    assert update_ticket("T-1001", "resolved", "Fixed via KB-003") == {
        "ok": True,
        "data": {"ticket_id": "T-1001", "status": "resolved"},
    }
    data = get_ticket("T-1001")["data"]
    assert data["status"] == "resolved" and data["notes"] == ["Fixed via KB-003"]


def test_update_creates_unknown_ticket():
    assert update_ticket("EV-001", "escalated", "Security terms")["ok"] is True
    data = get_ticket("EV-001")["data"]
    assert data["status"] == "escalated" and data["notes"] == ["Security terms"]


def test_update_is_idempotent_for_identical_calls():
    for _ in range(3):
        assert update_ticket("T-1001", "escalated", "Same note")["ok"] is True
    assert get_ticket("T-1001")["data"]["notes"] == ["Same note"]


def test_a_changed_call_is_recorded_and_a_return_to_old_value_is_a_new_write():
    update_ticket("T-1001", "open", "first")
    update_ticket("T-1001", "resolved", "second")
    update_ticket("T-1001", "open", "first")
    assert get_ticket("T-1001")["data"]["notes"] == ["first", "second", "first"]


def test_empty_note_changes_status_without_adding_a_note():
    update_ticket("T-1001", "escalated", "")
    data = get_ticket("T-1001")["data"]
    assert data["status"] == "escalated" and data["notes"] == []


@pytest.mark.parametrize(
    "args",
    [
        ("T-1001", "closed", "x"),
        ("T-1001", "", "x"),
        ("T-1001", "open", "n" * 1001),
        ("T-1001", "open", None),
        ("bad id", "open", "x"),
    ],
)
def test_update_ticket_invalid_input(args):
    assert error_code(update_ticket(*args)) == "INVALID_INPUT"


def test_failed_update_changes_nothing():
    before = get_ticket("T-1001")
    update_ticket("T-1001", "closed", "x")
    assert get_ticket("T-1001") == before


def test_ticket_store_is_capped_and_seeds_survive():
    for n in range(MAX_TICKETS + 50):
        update_ticket(f"X-{n}", "open", "")
    assert get_ticket("T-1001")["ok"] is True
    assert error_code(get_ticket("X-0")) == "NOT_FOUND"  # oldest evicted
    assert get_ticket(f"X-{MAX_TICKETS + 49}")["ok"] is True


# ---------- add_comment ----------


def test_add_comment_ids_count_up():
    first = add_comment("T-1001", "Please restart the client.", "requester")
    second = add_comment("T-1001", "Internal: checked logs.", "internal")
    assert first["data"]["comment_id"] == "C-0001"
    assert second["data"]["comment_id"] == "C-0002"
    assert [c["visibility"] for c in get_comments("T-1001")] == ["requester", "internal"]


def test_identical_comment_returns_the_existing_id():
    a = add_comment("T-1001", "Same text", "requester")
    b = add_comment("T-1001", "Same text", "requester")
    assert a == b and len(get_comments("T-1001")) == 1


def test_same_text_on_another_ticket_is_a_new_comment():
    a = add_comment("T-1001", "Same text", "requester")
    b = add_comment("T-1002", "Same text", "requester")
    assert a["data"]["comment_id"] != b["data"]["comment_id"]


def test_comment_on_unknown_ticket_is_allowed():
    assert add_comment("EV-009", "hello", "internal")["ok"] is True


@pytest.mark.parametrize(
    "args",
    [
        ("T-1001", "", "requester"),
        ("T-1001", "   ", "requester"),
        ("T-1001", "x" * 1001, "requester"),
        ("T-1001", "ok", "public"),
        ("T-1001", "ok", ""),
        ("", "ok", "internal"),
        ("T-1001", None, "internal"),
    ],
)
def test_add_comment_invalid_input(args):
    assert error_code(add_comment(*args)) == "INVALID_INPUT"


# ---------- isolation and fault injection ----------


def test_reset_state_isolates_tests():
    update_ticket("T-1001", "resolved", "changed")
    add_comment("T-1001", "hi", "internal")
    reset_state()
    assert get_ticket("T-1001")["data"]["status"] == "open"
    assert get_comments("T-1001") == []
    assert add_comment("T-1001", "again", "internal")["data"]["comment_id"] == "C-0001"


def test_fault_injection_applies_to_itsm_tools(monkeypatch):
    monkeypatch.setenv("FAULT_INJECT", json.dumps({"search_kb": "TIMEOUT"}))
    result = search_kb("vpn")
    assert error_code(result) == "TIMEOUT" and result["error"]["retryable"] is True
    assert get_ticket("T-1001")["ok"] is True


def test_unexpected_exception_becomes_internal_envelope(monkeypatch):
    def boom():
        raise RuntimeError("secret internals")

    monkeypatch.setattr("mcp_servers.itsm_logic.load_kb", boom)
    result = search_kb("vpn")
    assert error_code(result) == "INTERNAL" and "secret" not in result["error"]["message"]
