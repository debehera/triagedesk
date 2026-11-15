"""Integrity checks for the mock data in data/*.json and the PRD user stories they must support.

These tests read the JSON files directly. Loaders (src/data.py) arrive on Day 3.
"""

import json
import re
from pathlib import Path

import pytest

from src.config import Settings
from src.schemas import Category, Sensitivity

DATA = Path(__file__).resolve().parent.parent / "data"

# Roles that no mock user holds on purpose: access to r-08 can never be "eligible" (EV-028).
INTENTIONALLY_UNHELD_ROLES = {"IT Operations Lead"}

# Same patterns as src/safety.py will define on Day 7; KB text must never trip them.
SECRET_PATTERNS = {
    "password_assignment": r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+",
    "password_is": r"(?i)(your|the|new|temporary|temp)\s+password\s+is\s+\S+",
    "api_key_sk": r"\bsk-[A-Za-z0-9_-]{20,}",
    "aws_key": r"\bAKIA[0-9A-Z]{16}\b",
    "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "bearer": r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}",
    "otp_code": r"(?i)\b(otp|mfa|2fa|verification)\s*(code)?\s*(is|:)\s*\d{4,8}\b",
}

# Requester of each public sample ticket (blueprint Appendix E)
PUBLIC_SAMPLE_REQUESTERS = {
    "EV-001": "u-101",
    "EV-003": "u-103",
    "EV-005": "u-104",
    "EV-013": "u-102",
    "EV-020": "u-101",
    "EV-024": "u-104",
    "EV-029": "u-103",
    "EV-037": "u-106",
}


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def users() -> dict[str, dict]:
    return {u["id"]: u for u in load("users.json")}


@pytest.fixture(scope="module")
def resources() -> dict[str, dict]:
    return {r["id"]: r for r in load("resources.json")}


@pytest.fixture(scope="module")
def access() -> dict[str, list[str]]:
    return load("access.json")


@pytest.fixture(scope="module")
def kb() -> list[dict]:
    return load("kb.json")


def eligible(user: dict, resource: dict) -> bool:
    return "*" in resource["allowed_roles"] or user["role"] in resource["allowed_roles"]


# ---------- users ----------


def test_user_ids_unique_and_well_formed(users):
    raw = load("users.json")
    assert len(raw) == len(users) == 15
    assert all(re.fullmatch(r"u-\d{3}", u["id"]) for u in raw)


def test_managers_exist_and_are_top_level(users):
    for u in users.values():
        if u["manager_id"] is not None:
            assert u["manager_id"] in users
            assert users[u["manager_id"]]["manager_id"] is None


def test_only_u115_is_disabled(users):
    disabled = {uid for uid, u in users.items() if u["status"] == "disabled"}
    assert disabled == {"u-115"}


def test_emails_use_example_domain(users):
    assert all(u["email"].endswith("@example.com") for u in users.values())


# ---------- resources and access ----------


def test_resource_ids_unique_and_sensitivity_valid(resources):
    raw = load("resources.json")
    assert len(raw) == len(resources) == 10
    assert all(re.fullmatch(r"r-\d{2}", r["id"]) for r in raw)
    valid = {s.value for s in Sensitivity}
    assert all(r["sensitivity"] in valid for r in raw)
    assert all(2 <= len(r["aliases"]) <= 4 for r in raw)


def test_every_allowed_role_is_held_by_someone_or_intentionally_not(users, resources):
    held = {u["role"] for u in users.values()}
    for r in resources.values():
        for role in r["allowed_roles"]:
            assert role == "*" or role in held or role in INTENTIONALLY_UNHELD_ROLES


def test_access_references_exist(users, resources, access):
    assert set(access) == set(users)
    for uid, rids in access.items():
        assert set(rids) <= set(resources), uid
        assert len(rids) == len(set(rids))


def test_disabled_user_has_no_access(access):
    assert access["u-115"] == []


@pytest.mark.parametrize(
    ("user_id", "resource_id", "sensitivity", "is_eligible", "has_access"),
    [
        ("u-101", "r-04", "standard", True, False),
        ("u-104", "r-05", "restricted", True, False),
        ("u-102", "r-07", "privileged", True, False),
        ("u-108", "r-01", "standard", False, False),
        ("u-109", "r-08", "privileged", False, False),
        ("u-107", "r-09", "standard", True, False),
        ("u-108", "r-02", "standard", True, False),
        ("u-102", "r-03", "standard", True, False),
    ],
)
def test_access_matrix_used_by_evals(
    users, resources, access, user_id, resource_id, sensitivity, is_eligible, has_access
):
    resource = resources[resource_id]
    assert resource["sensitivity"] == sensitivity
    assert eligible(users[user_id], resource) is is_eligible
    assert (resource_id in access[user_id]) is has_access


# ---------- knowledge base ----------


def test_kb_ids_and_categories(kb):
    ids = [a["id"] for a in kb]
    assert ids == [f"KB-{n:03d}" for n in range(1, 13)]
    valid = {c.value for c in Category}
    assert all(a["category"] in valid for a in kb)


def test_every_category_except_other_has_an_article(kb):
    covered = {a["category"] for a in kb}
    assert covered == {c.value for c in Category} - {"other"}


def test_kb_article_shape(kb):
    for a in kb:
        assert 3 <= len(a["steps"]) <= 5, a["id"]
        assert a["title"].strip()
        assert a["keywords"] and all(k == k.lower() and len(k) >= 3 for k in a["keywords"]), a["id"]


@pytest.mark.parametrize("name", SECRET_PATTERNS)
def test_kb_steps_contain_no_secret_like_text(kb, name):
    pattern = re.compile(SECRET_PATTERNS[name])
    for a in kb:
        for step in a["steps"]:
            assert not pattern.search(step), (a["id"], step)


# ---------- pricing and settings ----------


def test_pricing_covers_default_models():
    pricing = load("pricing.json")
    for model in Settings.from_env({}).models.values():
        entry = pricing[model]
        assert set(entry) == {
            "input_per_mtok",
            "output_per_mtok",
            "cache_read_per_mtok",
            "cache_write_per_mtok",
        }
        assert all(v > 0 for v in entry.values())


# ---------- PRD user stories: does the data support each one? ----------


def test_us1_vpn_ticket_has_user_and_cited_article(users, kb):
    """US-1: VPN authentication failure -> AUTO_RESOLVED citing a real KB article."""
    assert users["u-101"]["status"] == "active"
    article = next(a for a in kb if a["id"] == "KB-003")
    assert article["category"] == "vpn_network"


def test_us2_restricted_share_is_resolvable_and_needs_approval(users, resources, access):
    """US-2: access to a restricted share -> PENDING_APPROVAL."""
    by_alias = {alias: r for r in resources.values() for alias in r["aliases"]}
    finance = by_alias["finance share"]
    assert finance["id"] == "r-05" and finance["sensitivity"] == "restricted"
    assert eligible(users["u-104"], finance) and "r-05" not in access["u-104"]


def test_us3_phishing_has_requester_and_article(users, kb):
    """US-3: suspected phishing -> ESCALATED with a handoff."""
    assert users["u-103"]["status"] == "active"
    assert any(a["category"] == "security_incident" for a in kb)


def test_us5_injection_targets_exist(users, resources):
    """US-5: injection tickets target privileged resources the requester may not hold."""
    assert resources["r-08"]["sensitivity"] == "privileged"
    assert not eligible(users["u-106"], resources["r-08"])
    assert resources["r-07"]["sensitivity"] == "privileged"


def test_us6_public_sample_requesters_exist_and_are_active(users):
    """US-6: the 8 public samples can run without sign-up."""
    assert len(PUBLIC_SAMPLE_REQUESTERS) == 8
    for requester in PUBLIC_SAMPLE_REQUESTERS.values():
        assert users[requester]["status"] == "active"
