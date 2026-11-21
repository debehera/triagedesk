"""pre_tool_check: least privilege at the tool boundary."""

import pytest

from src.guardrails import TOOL_ARGS, GuardrailBlocked, pre_tool_check
from src.mcp_hub import READ_ONLY_TOOLS, WRITE_TOOLS
from src.schemas import Ticket

TICKET = Ticket(id="EV-001", subject="s", body="b", requester_id="u-101")
READ = set(READ_ONLY_TOOLS)


def check(name, args, allowed=READ):
    pre_tool_check(name, args, ticket=TICKET, allowed=allowed)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("get_user", {"user_id": "u-101"}),
        ("check_access", {"user_id": "u-101", "resource_id": "r-05"}),
        ("find_resource", {"query": "finance share"}),
        ("search_kb", {"query": "vpn authentication failed"}),
        ("search_kb", {"query": "vpn", "category": "vpn_network", "limit": 5}),
        ("search_kb", {"query": "vpn", "category": None, "limit": 1}),
        ("get_ticket", {"ticket_id": "T-1001"}),
    ],
)
def test_legal_calls_pass(name, args):
    check(name, args)


@pytest.mark.parametrize("name", sorted(WRITE_TOOLS))
def test_write_tools_are_blocked_for_the_model(name):
    with pytest.raises(GuardrailBlocked, match="not allowed"):
        check(name, {"ticket_id": "T-1"})


def test_unknown_tool_is_blocked():
    with pytest.raises(GuardrailBlocked, match="not allowed"):
        check("delete_everything", {})
    with pytest.raises(GuardrailBlocked, match="unknown"):
        check("delete_everything", {}, allowed={"delete_everything"})


def test_restricted_allow_list_is_respected():
    with pytest.raises(GuardrailBlocked, match="not allowed"):
        check("search_kb", {"query": "vpn"}, allowed={"get_user"})


@pytest.mark.parametrize("tool", ["get_user", "check_access"])
def test_only_the_requester_may_be_looked_up(tool):
    args = {"user_id": "u-110"} | ({"resource_id": "r-05"} if tool == "check_access" else {})
    with pytest.raises(GuardrailBlocked, match="requester"):
        check(tool, args)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("get_user", {"user_id": "u-1"}),
        ("get_user", {"user_id": "U-101"}),
        ("get_user", {"user_id": "u-101 "}),
        ("get_user", {"user_id": 101}),
        ("get_user", {"user_id": None}),
        ("check_access", {"user_id": "u-101", "resource_id": "r-5"}),
        ("check_access", {"user_id": "u-101", "resource_id": "R-05"}),
        ("check_access", {"user_id": "u-101", "resource_id": ["r-05"]}),
        ("get_ticket", {"ticket_id": "../etc/passwd"}),
        ("get_ticket", {"ticket_id": ""}),
        ("get_ticket", {"ticket_id": "x" * 65}),
        ("get_ticket", {"ticket_id": 7}),
    ],
)
def test_malformed_ids_are_blocked(name, args):
    with pytest.raises(GuardrailBlocked, match="malformed"):
        check(name, args)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("get_user", {"user_id": "u-101", "admin": True}),
        ("search_kb", {"query": "vpn", "limt": 3}),
        ("find_resource", {"query": "x", "user_id": "u-101"}),
    ],
)
def test_unknown_argument_names_are_blocked(name, args):
    with pytest.raises(GuardrailBlocked, match="unknown argument"):
        check(name, args)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("search_kb", {"query": ""}),
        ("search_kb", {"query": "   "}),
        ("search_kb", {"query": "x" * 201}),
        ("search_kb", {"query": None}),
        ("search_kb", {"query": 5}),
        ("find_resource", {"query": "x" * 101}),
        ("search_kb", {"query": "vpn\nIgnore previous"}),
        ("search_kb", {"query": "vpn\x00"}),
    ],
)
def test_bad_queries_are_blocked(name, args):
    with pytest.raises(GuardrailBlocked, match="query"):
        check(name, args)


@pytest.mark.parametrize("limit", [0, 6, 50, -1, "3", 2.5, True, None])
def test_bad_limits_are_blocked(limit):
    with pytest.raises(GuardrailBlocked, match="limit"):
        check("search_kb", {"query": "vpn", "limit": limit})


def test_unknown_category_is_blocked():
    with pytest.raises(GuardrailBlocked, match="category"):
        check("search_kb", {"query": "vpn", "category": "nonsense"})


def test_non_dict_arguments_are_blocked():
    with pytest.raises(GuardrailBlocked, match="object"):
        check("get_user", ["u-101"])  # type: ignore[arg-type]


def test_reasons_never_echo_values():
    with pytest.raises(GuardrailBlocked) as info:
        check("get_user", {"user_id": "u-666"})
    assert "u-666" not in str(info.value)


def test_every_real_tool_has_an_argument_list():
    assert set(TOOL_ARGS) == set(READ_ONLY_TOOLS) | set(WRITE_TOOLS)
