"""Tests for src/data.py (loaders and the eligibility rule)."""

import pytest

from src.data import is_eligible, load_access, load_kb, load_pricing, load_resources, load_users
from src.schemas import Sensitivity


def test_loader_counts():
    assert len(load_users()) == 15
    assert len(load_resources()) == 10
    assert len(load_access()) == 15
    assert len(load_kb()) == 12


def test_users_are_typed_and_exclude_email():
    user = load_users()["u-104"]
    assert (user.name, user.department, user.status) == ("Dev Patel", "Finance", "active")
    assert "email" not in user.model_dump()
    assert load_users()["u-115"].status == "disabled"


def test_resources_are_typed():
    resource = load_resources()["r-05"]
    assert resource.sensitivity is Sensitivity.RESTRICTED
    assert "finance share" in resource.aliases


def test_access_is_a_set_per_user():
    assert load_access()["u-103"] == {"r-03", "r-05"}
    assert load_access()["u-115"] == frozenset()


def test_kb_articles_are_typed():
    assert [a.id for a in load_kb()][:2] == ["KB-001", "KB-002"]


def test_pricing_drops_the_source_note_and_works_with_empty_environment(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pricing = load_pricing()
    assert "_source" not in pricing
    assert set(pricing) == {"claude-haiku-5-5", "claude-sonnet-5-5"}


def test_loaders_are_cached():
    assert load_users() is load_users()


@pytest.mark.parametrize(
    ("user_id", "resource_id", "expected"),
    [
        ("u-101", "r-04", True),
        ("u-104", "r-05", True),
        ("u-102", "r-07", True),
        ("u-108", "r-01", False),
        ("u-109", "r-08", False),
        ("u-107", "r-09", True),
        ("u-108", "r-02", True),
        ("u-102", "r-03", True),
    ],
)
def test_is_eligible_matches_the_eval_matrix(user_id, resource_id, expected):
    assert is_eligible(load_users()[user_id], load_resources()[resource_id]) is expected
