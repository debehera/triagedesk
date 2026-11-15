"""Loaders for the mock reference data in data/*.json (blueprint Day 3, step 1b).

The JSON files are the "database" (docs/SCHEMA.md, storage strategy S1). Each loader reads
its file once and caches the result, so repeated calls are free. Treat everything returned
here as read-only: callers must not modify it, because the cache hands out the same objects.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.schemas import Category, Sensitivity, UserRecord

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Resource(BaseModel):
    """A system, share or application that a ticket can ask access to (data/resources.json)."""

    id: str
    name: str
    aliases: list[str]
    sensitivity: Sensitivity
    allowed_roles: list[str]


class KBArticle(BaseModel):
    """One knowledge-base article (data/kb.json)."""

    id: str
    title: str
    category: Category
    keywords: list[str]
    steps: list[str]
    last_reviewed: str


def _read(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache
def load_users() -> dict[str, UserRecord]:
    """All mock employees keyed by id (u-101 ...). The e-mail field in the file is ignored."""
    return {u["id"]: UserRecord.model_validate(u) for u in _read("users.json")}


@lru_cache
def load_resources() -> dict[str, Resource]:
    """All resources keyed by id (r-01 ...)."""
    return {r["id"]: Resource.model_validate(r) for r in _read("resources.json")}


@lru_cache
def load_access() -> dict[str, frozenset[str]]:
    """Which resources each user already holds: user id -> set of resource ids."""
    return {uid: frozenset(rids) for uid, rids in _read("access.json").items()}


@lru_cache
def load_kb() -> list[KBArticle]:
    """The knowledge base, in file order (KB-001 ...)."""
    return [KBArticle.model_validate(a) for a in _read("kb.json")]


@lru_cache
def load_pricing() -> dict[str, dict[str, float]]:
    """USD per million tokens, keyed by model id. The `_source` note in the file is dropped."""
    return {k: v for k, v in _read("pricing.json").items() if not k.startswith("_")}


def is_eligible(user: UserRecord, resource: Resource) -> bool:
    """May this user's role request this resource? ("*" in allowed_roles means everyone.)"""
    return "*" in resource.allowed_roles or user.role in resource.allowed_roles
