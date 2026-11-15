"""Pure-logic tests for the directory tools (no MCP involved)."""

import json

import pytest

from mcp_servers.common import err, maybe_fault, ok
from mcp_servers.directory_logic import check_access, find_resource, get_user


def error_code(result: dict) -> str:
    assert result["ok"] is False
    return result["error"]["code"]


# ---------- envelope helpers ----------


def test_envelope_shapes():
    assert ok({"a": 1}) == {"ok": True, "data": {"a": 1}}
    assert err("X", "msg", retryable=True) == {
        "ok": False,
        "error": {"code": "X", "message": "msg", "retryable": True},
    }


# ---------- get_user ----------


def test_get_user_valid_has_no_email():
    result = get_user("u-104")
    assert result["ok"] is True
    assert result["data"]["department"] == "Finance"
    assert set(result["data"]) == {"id", "name", "department", "role", "manager_id", "status"}


def test_get_user_unknown_is_not_retryable():
    result = get_user("u-999")
    assert error_code(result) == "NOT_FOUND"
    assert result["error"]["retryable"] is False


@pytest.mark.parametrize(
    "bad", ["104", "", "u-1; DROP", "u-12", "u-1234", "u-101\n", "u-١٢٣", None]
)
def test_get_user_malformed_ids(bad):
    assert error_code(get_user(bad)) == "INVALID_INPUT"


def test_get_user_returns_disabled_account():
    assert get_user("u-115")["data"]["status"] == "disabled"


# ---------- find_resource ----------


@pytest.mark.parametrize(
    ("query", "first"),
    [
        ("the finance share", "r-05"),
        ("prod db", "r-07"),
        ("admin access", "r-08"),
        ("Finance Drive", "r-05"),
        ("payroll", "r-10"),
        ("CRM", "r-09"),
        ("  the   Company WIKI ", "r-03"),
    ],
)
def test_find_resource_best_match_first(query, first):
    result = find_resource(query)
    assert result["ok"] is True
    assert result["data"]["resources"][0]["id"] == first


def test_find_resource_returns_at_most_three_with_sensitivity():
    resources = find_resource("shared drive")["data"]["resources"]
    assert 1 <= len(resources) <= 3
    assert all(set(r) == {"id", "name", "sensitivity"} for r in resources)


@pytest.mark.parametrize("bad", ["", "   ", "x" * 101, None])
def test_find_resource_invalid_input(bad):
    assert error_code(find_resource(bad)) == "INVALID_INPUT"


def test_find_resource_nothing_matches():
    assert error_code(find_resource("zzzz")) == "NOT_FOUND"


def test_find_resource_is_deterministic():
    assert find_resource("shared drive") == find_resource("shared drive")


# ---------- check_access (the eight pairs used by the eval set) ----------


@pytest.mark.parametrize(
    ("user_id", "resource_id", "sensitivity", "has_access", "eligible"),
    [
        ("u-101", "r-04", "standard", False, True),
        ("u-104", "r-05", "restricted", False, True),
        ("u-102", "r-07", "privileged", False, True),
        ("u-108", "r-01", "standard", False, False),
        ("u-109", "r-08", "privileged", False, False),
        ("u-107", "r-09", "standard", False, True),
        ("u-108", "r-02", "standard", False, True),
        ("u-102", "r-03", "standard", False, True),
    ],
)
def test_check_access_matrix(user_id, resource_id, sensitivity, has_access, eligible):
    result = check_access(user_id, resource_id)
    assert result["ok"] is True
    data = result["data"]
    assert data["sensitivity"] == sensitivity
    assert data["eligible"] is eligible
    assert data["has_access"] is has_access


def test_check_access_reports_held_resource():
    data = check_access("u-103", "r-05")["data"]
    assert data["has_access"] is True and data["resource_name"] == "Finance Shared Drive"


def test_check_access_data_validates_as_access_check_model():
    from src.schemas import AccessCheck

    AccessCheck.model_validate(check_access("u-104", "r-05")["data"])


def test_check_access_unknown_resource_and_user():
    assert error_code(check_access("u-104", "r-99")) == "NOT_FOUND"
    assert error_code(check_access("u-999", "r-05")) == "NOT_FOUND"


@pytest.mark.parametrize(("user_id", "resource_id"), [("u-104", "05"), ("104", "r-05"), ("", "")])
def test_check_access_malformed(user_id, resource_id):
    assert error_code(check_access(user_id, resource_id)) == "INVALID_INPUT"


# ---------- fault injection ----------


@pytest.mark.parametrize(
    ("kind", "code", "retryable"),
    [
        ("TIMEOUT", "TIMEOUT", True),
        ("INTERNAL", "INTERNAL", True),
        ("NOT_FOUND", "NOT_FOUND", False),
    ],
)
def test_injected_faults(monkeypatch, kind, code, retryable):
    monkeypatch.setenv("FAULT_INJECT", json.dumps({"get_user": kind}))
    result = get_user("u-101")
    assert error_code(result) == code and result["error"]["retryable"] is retryable
    assert find_resource("prod db")["ok"] is True  # other tools are unaffected


def test_timeout_once_fails_then_succeeds(monkeypatch):
    monkeypatch.setenv("FAULT_INJECT", '{"get_user": "TIMEOUT_ONCE"}')
    assert error_code(get_user("u-101")) == "TIMEOUT"
    assert get_user("u-101")["ok"] is True
    assert get_user("u-101")["ok"] is True


def test_bad_fault_config_is_ignored(monkeypatch):
    monkeypatch.setenv("FAULT_INJECT", "not json")
    assert maybe_fault("get_user") is None
    monkeypatch.setenv("FAULT_INJECT", '{"get_user": "EXPLODE"}')
    assert get_user("u-101")["ok"] is True


def test_unexpected_exception_becomes_internal_envelope(monkeypatch):
    def boom():
        raise RuntimeError("disk on fire")

    monkeypatch.setattr("mcp_servers.directory_logic.load_users", boom)
    result = get_user("u-101")
    assert error_code(result) == "INTERNAL" and result["error"]["retryable"] is True
    assert "disk" not in result["error"]["message"]  # internals are not leaked
