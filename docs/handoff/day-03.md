# Handoff: Day 3 -> Day 4

## State at the end of Day 3
- Branch `day-03-directory-server` (merge to `main` after the Inspector check).
- New: `src/data.py` (loaders + `Resource`, `KBArticle` models + `is_eligible`), `mcp_servers/common.py`, `directory_logic.py`, `directory_server.py`, `tests/conftest.py`, `test_data.py`, `test_directory_logic.py`, `test_directory_stdio.py`.
- 126 tests pass offline (62 from Day 2 + 64 new); `ruff check .` clean.

## Exports Day 4 can reuse
- `mcp_servers/common.py`: `ok(data)`, `err(code, message, retryable=False)`, `log(msg)` (stderr), `valid_user_id`, `valid_resource_id`, `maybe_fault(tool_name)`, `reset_faults()`, and the decorator `@tool_guard("tool_name")` (fault injection first, then any unexpected exception becomes an `INTERNAL` envelope).
- `mcp_servers/directory_logic.py`: `get_user(user_id)`, `find_resource(query)`, `check_access(user_id, resource_id)`.
- `src/data.py`: `load_users()`, `load_resources()`, `load_access()` (user -> frozenset), `load_kb()` (list of `KBArticle`), `load_pricing()` (no `_source`), `is_eligible(user, resource)`.
- Fault injection: env `FAULT_INJECT` as JSON, e.g. `{"get_user": "TIMEOUT_ONCE"}`; kinds `TIMEOUT`, `INTERNAL`, `NOT_FOUND`, `TIMEOUT_ONCE`. Read at call time. `tests/conftest.py` clears it and resets the once-state for every test.
- Server pattern: `directory_server.py` inserts the repo root into `sys.path`, imports the logic functions, registers them with `mcp.tool()(fn)`. Copy it for `itsm_server.py`.

## Differences from the blueprint
1. `@tool_guard` decorator instead of an explicit fault line in each function (same behaviour, plus a catch-all so a tool never leaks a traceback).
2. IDs are validated with `[0-9]` and `fullmatch` (not `\d` and `$`), so look-alike digits and a trailing newline are rejected.
3. `find_resource`: the "query contained in alias" rule applies only to queries of 3+ characters, so a one-letter query cannot match everything.
4. `.mcp.json` is NOT created today (needs Claude Code installed and a venv-specific python path); it moves to Day 11 with the rest of the Claude Code config.
5. `tests/conftest.py` created on Day 3 (the blueprint planned it for Day 5).

## Start Day 4 with
`git checkout main`, `git pull`, `git checkout -b day-04-itsm-server`, then the Day 4 section of the blueprint and `docs/API.md` sections 8.4-8.7.
