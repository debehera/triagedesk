"""Sanity checks for evals/tickets.jsonl and the classify-only runner (no API)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.agents.classifier import TOOL_NAME
from src.config import Settings
from src.data import load_kb, load_users
from src.schemas import Category, Ticket
from tests.fakes import FakeLLM, forced_tool_response

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = Settings.from_env({})

spec = importlib.util.spec_from_file_location("classify_only", ROOT / "evals" / "classify_only.py")
classify_only = importlib.util.module_from_spec(spec)
sys.modules["classify_only"] = classify_only  # dataclasses look the module up by name
spec.loader.exec_module(classify_only)

ITEMS = classify_only.load_items()


def test_thirty_three_unique_sequential_tickets():
    assert [i["id"] for i in ITEMS] == [f"EV-{n:03d}" for n in range(1, 34)]


def test_every_ticket_is_a_valid_ticket_with_valid_labels():
    users, kb_ids = load_users(), {a.id for a in load_kb()}
    categories = {c.value for c in Category}
    for item in ITEMS:
        Ticket.model_validate({k: item[k] for k in ("id", "subject", "body", "requester_id")})
        exp = item["expected"]
        assert exp["category"] in categories
        assert set(exp["acceptable_categories"]) <= categories
        assert item["requester_id"] in users
        assert exp["kb_article"] is None or exp["kb_article"] in kb_ids
        assert item["split"] in {"dev", "holdout"}


def test_tickets_never_mention_kb_ids():
    assert not any("KB-" in i["subject"] + i["body"] for i in ITEMS)


def test_public_samples_and_split_counts():
    public = {i["id"] for i in ITEMS if i["public"]}
    assert public == {"EV-001", "EV-003", "EV-005", "EV-013", "EV-020", "EV-024", "EV-029"}
    assert sum(i["split"] == "dev" for i in ITEMS) == 20
    assert all(i["split"] == "dev" for i in ITEMS if i["public"])


def good(category="vpn_network", severity="P3", confidence=0.9, **extra):
    return forced_tool_response(
        TOOL_NAME,
        {
            "category": category,
            "severity": severity,
            "confidence": confidence,
            "affected_system": "x",
            "summary": "s",
            **extra,
        },
    )


def test_holdout_is_refused_by_default():
    with pytest.raises(SystemExit):
        classify_only.select(ITEMS, split="holdout", ids=None, include_holdout=False)
    with pytest.raises(SystemExit):
        classify_only.select(ITEMS, split="all", ids=None, include_holdout=False)
    with pytest.raises(SystemExit):
        classify_only.select(ITEMS, split="dev", ids={"EV-002"}, include_holdout=False)


def test_default_selection_is_the_twenty_dev_tickets():
    chosen = classify_only.select(ITEMS, split="dev", ids=None, include_holdout=False)
    assert len(chosen) == 20 and all(i["split"] == "dev" for i in chosen)


async def test_scoring_counts_acceptable_categories_and_severity_tolerance():
    items = [i for i in ITEMS if i["id"] in {"EV-001", "EV-014", "EV-005"}]
    llm = FakeLLM(
        [
            good("vpn_network", "P3"),  # EV-001 exact
            good("password_reset", "P4", 0.4, risk_flags=["ambiguous"]),  # EV-005 wrong cat, ok sev
            good("vpn_network", "P1", 0.5),  # EV-014 acceptable cat, severity off by 2
        ]
    )
    rows = await classify_only.run_all(llm, items, SETTINGS, concurrency=1, max_cost=10)
    by_id = {r.id: r for r in rows}
    assert by_id["EV-001"].category_ok and by_id["EV-001"].severity_ok
    assert not by_id["EV-005"].category_ok and by_id["EV-005"].severity_ok
    assert by_id["EV-014"].category_ok and not by_id["EV-014"].severity_ok
    summary = classify_only.summarize(rows)
    assert summary["category_accuracy"] == pytest.approx(2 / 3)
    assert summary["severity_within_1"] == pytest.approx(2 / 3)
    assert summary["low_confidence_ids"] == ["EV-005", "EV-014"]
    assert "MISMATCH" in classify_only.format_rows(rows)


async def test_a_failing_ticket_is_reported_not_fatal():
    items = [i for i in ITEMS if i["id"] in {"EV-001", "EV-003"}]
    llm = FakeLLM([forced_tool_response(TOOL_NAME, {})] * 3 + [good("password_reset")])
    rows = await classify_only.run_all(llm, items, SETTINGS, concurrency=1, max_cost=10)
    assert [r.error for r in rows] == ["ClassificationError", None]
    assert classify_only.summarize(rows)["errors"] == ["EV-001"]


async def test_cost_cap_stops_starting_new_tickets():
    items = [i for i in ITEMS if i["id"] in {"EV-001", "EV-003", "EV-005"}]
    llm = FakeLLM([good(), good("password_reset"), good("software_install", "P4")])
    rows = await classify_only.run_all(llm, items, SETTINGS, concurrency=1, max_cost=0.0005)
    assert len(rows) == 1 and len(llm.calls) == 1


def test_the_file_is_valid_jsonl_with_lf_endings():
    raw = (ROOT / "evals" / "tickets.jsonl").read_bytes()
    assert b"\r" not in raw
    assert all(json.loads(line) for line in raw.decode().splitlines())


# ---------- access and security tickets (EV-020..033) ----------

ACCESS = [i for i in ITEMS if i["tags"][0].startswith("access")]
SECURITY = [i for i in ITEMS if i["tags"][0] == "security"]


def test_group_sizes_match_the_blueprint():
    assert len(ACCESS) == 9 and len(SECURITY) == 5
    assert sum(i["tags"][0] == "access-standard" for i in ITEMS) == 4
    assert sum(i["tags"][0] == "access-restricted" for i in ITEMS) == 5


def test_access_labels_agree_with_the_reference_data():
    """Expected outcome must equal what G2 would decide from data/*.json (no hand-made drift)."""
    from src.data import is_eligible, load_access, load_resources, load_users

    resources, users, held = load_resources(), load_users(), load_access()
    wanted = {
        "EV-020": "r-04",
        "EV-021": "r-02",
        "EV-022": "r-09",
        "EV-023": "r-03",
        "EV-024": "r-05",
        "EV-025": "r-06",
        "EV-026": "r-07",
        "EV-027": "r-01",
        "EV-028": "r-08",
    }
    assert set(wanted) == {i["id"] for i in ACCESS}
    for item in ACCESS:
        resource, user = resources[wanted[item["id"]]], users[item["requester_id"]]
        assert resource.id not in held[user.id], item["id"]  # nobody asks for what they have
        needs_approval = resource.sensitivity.value != "standard" or not is_eligible(user, resource)
        assert item["expected"]["outcome"] == (
            "PENDING_APPROVAL" if needs_approval else "AUTO_RESOLVED"
        ), item["id"]
        assert item["expected"]["high_risk"] is (resource.sensitivity.value != "standard"), item[
            "id"
        ]


def test_security_tickets_are_escalated_and_high_risk():
    for item in SECURITY:
        assert item["expected"]["category"] == "security_incident"
        assert item["expected"]["outcome"] == "ESCALATED" and item["expected"]["high_risk"]


def test_the_code_side_net_catches_every_security_ticket():
    """CR-2: G1 must not depend on the model recognising the incident."""
    from src.safety import detect_security_terms

    for item in SECURITY:
        assert detect_security_terms(item["subject"] + " " + item["body"]), item["id"]


def test_no_other_ticket_trips_the_detectors():
    """False-positive check over every non-security ticket in the set."""
    from src.safety import injection_matches, security_matches

    for item in ITEMS:
        text = item["subject"] + " " + item["body"]
        assert injection_matches(text) == [], item["id"]
        if item["tags"][0] != "security":
            assert security_matches(text) == [], (item["id"], security_matches(text))
