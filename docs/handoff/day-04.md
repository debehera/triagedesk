# Handoff: Day 4 -> Day 5

## State at the end of Day 4
- Branch `day-04-itsm-server` (merge to `main` after the checks).
- New: `mcp_servers/itsm_logic.py`, `mcp_servers/itsm_server.py`, `data/tickets_seed.json`, `tests/test_itsm_logic.py`, `tests/test_itsm_stdio.py`. Modified: `src/data.py` (`SeedTicket`, `TicketStatus`, `load_tickets_seed()`), `docs/API.md` (search_kb scoring note).
- 198 tests pass offline; `ruff check .` clean. Both servers verified in the MCP Inspector.

## The seven tools (for the Day 5 hub)
| Tool | Server file | Kind |
|------|-------------|------|
| `get_user`, `find_resource`, `check_access` | `mcp_servers/directory_server.py` (FastMCP name `directory`) | read |
| `search_kb`, `get_ticket` | `mcp_servers/itsm_server.py` (FastMCP name `itsm`) | read |
| `update_ticket`, `add_comment` | `mcp_servers/itsm_server.py` | write (coordinator commit step only) |

Start each server with `sys.executable` and the path of its `*_server.py`; tool names are unique across servers. Every tool returns the envelope `{"ok": true, "data": ...}` or `{"ok": false, "error": {code, message, retryable}}` as JSON text in `result.content[0].text`.

## `search_kb` output (matches `KBMatch`)
`{"matches": [{"id", "title", "category", "score", "steps": [...]}]}`, best first, at most `limit` (1-5, default 3). An empty list is success. Scores are multiples of 0.5.

## Behaviour to rely on
- `update_ticket` upserts (unknown ids are created with subject "(created by update_ticket)") and is idempotent for an identical `(ticket_id, status, note)`; at most 1,000 tickets, oldest non-seed evicted. Ticket ids: 1-64 characters of letters, digits, `.`, `_`, `-`, so `EV-001` and run ids are valid.
- `add_comment` works for unknown tickets; identical text on the same ticket returns the existing `C-0001`-style id. Comments are stored, not returned by `get_ticket`.
- State lives inside each server process: every new process starts from the seed. Tests call `reset_state()` (not a tool).
- `FAULT_INJECT` works for all seven tools (same JSON format; `TIMEOUT_ONCE` is per tool).

## Retrieval quality
All 12 articles are found first by their own title, and all 11 symptom queries from the blueprint rank the expected article first. No keyword fixes were needed.

## Differences from the blueprint
1. The category filter only boosts articles that already share a word with the query (before: a category alone could create matches). Test: `test_category_alone_never_creates_a_match`.
2. `.mcp.json` still deferred to Day 11 (see `day-03.md`); `claude mcp list` is therefore not part of Day 4.
3. `add_comment` and `update_ticket` accept ids that are not in the seed (needed for eval and web runs).

## Start Day 5 with
`git checkout main`, `git pull`, `git checkout -b day-05-llm-hub`. Day 5 needs an Anthropic API key and credits: add credits and set the Console spend limit first (see the Day 2 notes). Then follow the Day 5 section of the blueprint.
