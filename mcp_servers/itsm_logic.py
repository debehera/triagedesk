"""ITSM tools as plain functions (no MCP imports, so they are easy to unit test).

Two read tools (search_kb, get_ticket) and two write tools (update_ticket, add_comment).
The write tools are only ever called by the coordinator's commit step, never by the model
(docs/API.md section 7, ADR-014). Ticket state lives in memory and is lost when the server
process stops; that is intentional for the demo (docs/SCHEMA.md, storage strategy S3).
"""

from __future__ import annotations

import re
from typing import get_args

from mcp_servers.common import err, ok, tool_guard
from src.data import TicketStatus, load_kb, load_tickets_seed
from src.schemas import Category

# ---------- limits and constants ----------

TICKET_STATUSES: tuple[str, ...] = get_args(TicketStatus)
VISIBILITIES = ("requester", "internal")
MAX_TEXT = 1000
MAX_TICKETS = 1000
MAX_COMMENTS = 5000
MAX_QUERY = 200
TICKET_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "the and for not with can cant cannot this that from have has are was my our".split()
)

# ---------- in-memory state ----------

_TICKETS: dict[str, dict] = {}
_LAST_WRITE: dict[str, tuple[str, str]] = {}  # ticket id -> (status, note) of the latest update
_COMMENTS: list[dict] = []
_comment_counter = 0
_SEED_IDS: frozenset[str] = frozenset()


def reset_state() -> None:
    """Back to the seed tickets, no comments. Used by tests; NOT registered as a tool."""
    global _comment_counter, _SEED_IDS
    _TICKETS.clear()
    _LAST_WRITE.clear()
    _COMMENTS.clear()
    _comment_counter = 0
    for seed in load_tickets_seed():
        _TICKETS[seed.id] = {
            "id": seed.id,
            "subject": seed.subject,
            "status": seed.status,
            "notes": list(seed.notes),
        }
    _SEED_IDS = frozenset(_TICKETS)


reset_state()


def get_comments(ticket_id: str) -> list[dict]:
    """Test and debugging helper (not a tool): the comments stored for one ticket."""
    return [dict(c) for c in _COMMENTS if c["ticket_id"] == ticket_id]


# ---------- helpers ----------


def _tokens(text: str) -> set[str]:
    return {t for t in TOKEN_RE.findall(text.lower()) if len(t) >= 3 and t not in STOPWORDS}


def _valid_ticket_id(value: object) -> bool:
    return isinstance(value, str) and TICKET_ID_RE.fullmatch(value) is not None


def _valid_text(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        return False
    return allow_empty or bool(value.strip())


def _evict_if_full() -> None:
    """Keep at most MAX_TICKETS tickets by dropping the oldest non-seed ticket."""
    while len(_TICKETS) > MAX_TICKETS:
        victim = next((tid for tid in _TICKETS if tid not in _SEED_IDS), None)
        if victim is None:
            return
        del _TICKETS[victim]
        _LAST_WRITE.pop(victim, None)


# ---------- read tools ----------


@tool_guard("search_kb")
def search_kb(query: str, category: str | None = None, limit: int = 3) -> dict:
    """Search the IT knowledge base with a short symptom description (for example 'vpn
    authentication failed'). Use before proposing any fix. Returns up to `limit` ranked
    articles (id, title, category, score, steps); an empty list means no relevant article
    exists, so do not invent steps. `category` is optional and only boosts matching
    articles; `limit` is 1-5 (default 3).
    """
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY:
        return err("INVALID_INPUT", f"query must be 1-{MAX_QUERY} characters and not blank")
    if category is not None and category not in {c.value for c in Category}:
        return err("INVALID_INPUT", "category must be null or a valid category name")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        return err("INVALID_INPUT", "limit must be an integer from 1 to 5")

    query_tokens = _tokens(query)
    scored: list[tuple[float, str, dict]] = []
    for article in load_kb():
        score = 2.0 * len(query_tokens & _tokens(article.title))
        score += 1.0 * len(query_tokens & _tokens(" ".join(article.keywords)))
        if score < 1.0:
            continue  # no real word overlap: the category filter alone never creates a match
        if category is not None and article.category.value == category:
            score += 1.5
        scored.append(
            (
                score,
                article.id,
                {
                    "id": article.id,
                    "title": article.title,
                    "category": article.category.value,
                    "score": score,
                    "steps": list(article.steps),
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    return ok({"matches": [item[2] for item in scored[:limit]]})


@tool_guard("get_ticket")
def get_ticket(ticket_id: str) -> dict:
    """Fetch one ticket's subject, status and notes by its id (for example T-1001). Use it
    to see what has already been recorded on a ticket. Returns ok=false with NOT_FOUND when
    the id is unknown, or INVALID_INPUT when it is malformed.
    """
    if not _valid_ticket_id(ticket_id):
        return err("INVALID_INPUT", "ticket_id must be 1-64 letters, digits, '.', '_' or '-'")
    ticket = _TICKETS.get(ticket_id)
    if ticket is None:
        return err("NOT_FOUND", f"No ticket with id {ticket_id}")
    return ok(
        {
            "id": ticket["id"],
            "subject": ticket["subject"],
            "status": ticket["status"],
            "notes": list(ticket["notes"]),
        }
    )


# ---------- write tools (coordinator commit step only) ----------


@tool_guard("update_ticket")
def update_ticket(ticket_id: str, status: str, note: str) -> dict:
    """Write operation: record the final status and an internal note on a ticket. Only the
    coordinator's commit step calls this. status is one of open, resolved, pending_approval,
    escalated. Creates the ticket if it does not exist; repeating the identical call does
    not add a second note.
    """
    if not _valid_ticket_id(ticket_id):
        return err("INVALID_INPUT", "ticket_id must be 1-64 letters, digits, '.', '_' or '-'")
    if status not in TICKET_STATUSES:
        return err("INVALID_INPUT", f"status must be one of {', '.join(TICKET_STATUSES)}")
    if not _valid_text(note, allow_empty=True):
        return err("INVALID_INPUT", f"note must be a string of at most {MAX_TEXT} characters")

    ticket = _TICKETS.get(ticket_id)
    if ticket is None:
        ticket = {
            "id": ticket_id,
            "subject": "(created by update_ticket)",
            "status": status,
            "notes": [],
        }
        _TICKETS[ticket_id] = ticket
        _evict_if_full()
    if _LAST_WRITE.get(ticket_id) != (status, note):
        ticket["status"] = status
        if note:
            ticket["notes"].append(note)
        _LAST_WRITE[ticket_id] = (status, note)
    return ok({"ticket_id": ticket_id, "status": status})


@tool_guard("add_comment")
def add_comment(ticket_id: str, text: str, visibility: str) -> dict:
    """Write operation: add a comment to a ticket. Only the coordinator's commit step calls
    this. visibility is 'requester' (the requester can read it) or 'internal'. Returns the
    comment id; sending identical text for the same ticket returns the existing id instead
    of adding a duplicate.
    """
    global _comment_counter
    if not _valid_ticket_id(ticket_id):
        return err("INVALID_INPUT", "ticket_id must be 1-64 letters, digits, '.', '_' or '-'")
    if not _valid_text(text, allow_empty=False):
        return err("INVALID_INPUT", f"text must be 1-{MAX_TEXT} characters and not blank")
    if visibility not in VISIBILITIES:
        return err("INVALID_INPUT", "visibility must be 'requester' or 'internal'")

    for comment in _COMMENTS:
        if comment["ticket_id"] == ticket_id and comment["text"] == text:
            return ok({"ticket_id": ticket_id, "comment_id": comment["comment_id"]})
    _comment_counter += 1
    comment_id = f"C-{_comment_counter:04d}"
    _COMMENTS.append(
        {"comment_id": comment_id, "ticket_id": ticket_id, "text": text, "visibility": visibility}
    )
    if len(_COMMENTS) > MAX_COMMENTS:
        del _COMMENTS[0]
    return ok({"ticket_id": ticket_id, "comment_id": comment_id})
