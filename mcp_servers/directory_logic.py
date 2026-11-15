"""Directory tools as plain functions (no MCP imports, so they are easy to unit test).

directory_server.py registers these with FastMCP. The docstrings below are what the model
reads when it decides whether and how to call a tool, so they are written as short briefings.
"""

from __future__ import annotations

import re

from mcp_servers.common import err, ok, tool_guard, valid_resource_id, valid_user_id
from src.data import is_eligible, load_access, load_resources, load_users

_WORD_RE = re.compile(r"[a-z0-9]+")
MAX_RESULTS = 3


@tool_guard("get_user")
def get_user(user_id: str) -> dict:
    """Look up an employee by id (format u-123). Use this FIRST for any ticket to learn the
    requester's role, department and whether the account is active. Does not search by name.
    Returns ok/data with id, name, department, role, manager_id, status; or ok=false with
    code NOT_FOUND / INVALID_INPUT.
    """
    if not valid_user_id(user_id):
        return err("INVALID_INPUT", "user_id must look like u-123")
    user = load_users().get(user_id)
    if user is None:
        return err("NOT_FOUND", f"No user with id {user_id}")
    return ok(user.model_dump())  # no e-mail address: minimum data


def _score(query: str, query_words: set[str], resource) -> int:
    """Alias match (best of: equal 3, contained either way 2) plus 1 per shared name word."""
    alias_score = 0
    for alias in resource.aliases:
        if query == alias:
            alias_score = max(alias_score, 3)
        elif alias in query or (len(query) >= 3 and query in alias):
            alias_score = max(alias_score, 2)
    name_words = {w for w in _WORD_RE.findall(resource.name.lower()) if len(w) >= 3}
    return alias_score + len(query_words & name_words)


@tool_guard("find_resource")
def find_resource(query: str) -> dict:
    """Find resources (shares, apps, databases) by the words used in a ticket. Use when the
    ticket names a system or share in words ('the finance share'); returns up to 3 candidates,
    best first, each with id, name and sensitivity (standard, restricted or privileged).
    Does not check anyone's access. Returns ok=false with NOT_FOUND when nothing matches or
    INVALID_INPUT when the query is empty or longer than 100 characters.
    """
    if not isinstance(query, str) or not query.strip() or len(query) > 100:
        return err("INVALID_INPUT", "query must be 1-100 characters and not blank")
    text = " ".join(query.lower().split())
    words = {w for w in _WORD_RE.findall(text) if len(w) >= 3}
    scored = [(_score(text, words, r), r) for r in load_resources().values()]
    best = sorted(((s, r) for s, r in scored if s > 0), key=lambda pair: (-pair[0], pair[1].id))
    if not best:
        return err("NOT_FOUND", "No resource matches that description")
    return ok(
        {
            "resources": [
                {"id": r.id, "name": r.name, "sensitivity": r.sensitivity.value}
                for _, r in best[:MAX_RESULTS]
            ]
        }
    )


@tool_guard("check_access")
def check_access(user_id: str, resource_id: str) -> dict:
    """Check one user against one resource. Needs BOTH ids (user u-123, resource r-12; get the
    resource id from find_resource first). Returns ok/data with: resource_name, sensitivity
    (standard, restricted or privileged), has_access (the user already holds it) and eligible
    (the user's role is allowed to request it). Returns ok=false with NOT_FOUND for an unknown
    user or resource, or INVALID_INPUT for a malformed id.
    """
    if not valid_user_id(user_id):
        return err("INVALID_INPUT", "user_id must look like u-123")
    if not valid_resource_id(resource_id):
        return err("INVALID_INPUT", "resource_id must look like r-12")
    user = load_users().get(user_id)
    if user is None:
        return err("NOT_FOUND", f"No user with id {user_id}")
    resource = load_resources().get(resource_id)
    if resource is None:
        return err("NOT_FOUND", f"No resource with id {resource_id}")
    return ok(
        {
            "user_id": user.id,
            "resource_id": resource.id,
            "resource_name": resource.name,
            "sensitivity": resource.sensitivity.value,
            "has_access": resource_id in load_access().get(user_id, frozenset()),
            "eligible": is_eligible(user, resource),
        }
    )
