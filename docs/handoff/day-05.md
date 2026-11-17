# Handoff: Day 5 -> Day 6

## State at the end of Day 5
- Branch `day-05-agent-loop` (merge to `main` after the checks).
- New: `src/cost.py`, `src/llm.py`, `src/mcp_hub.py`, `src/prompts/` (`__init__.py`, `render.py`, `diagnostics.py`), `src/agents/diagnostics.py`, `scripts/smoke_diagnose.py`, `tests/fakes.py`, `tests/test_llm.py`, `tests/test_render.py`, `tests/test_mcp_hub.py`, `tests/test_diagnostics.py`.
- Modified: `src/guardrails.py` (skeleton, completed on Day 7), `pyproject.toml` (`addopts = "-m 'not live'"`, marker `live`).
- 284 tests pass offline (about 25-55 s, the MCP tests start real server processes); `ruff check .` clean.
- First live run (`python scripts/smoke_diagnose.py`, VPN ticket for u-101): 2 model calls, `get_user` + `search_kb`, no gaps, **4,752 input / 108 output tokens, $0.0106** on `claude-sonnet-5-5`. Most input tokens are the tool definitions plus the system prompt, so prompt caching (later) pays off.
- Account: $5 credits, auto-reload off, Console monthly limit $10. The API key lives only in the local, git-ignored `.env`.

## LLM wrapper (`src/llm.py`)
- `LLMClient` protocol: `await llm.create(role=, system=[...], messages=[...], tools=None, tool_choice=None, max_tokens=1024) -> LLMResponse`. `role` is `classifier | diagnostics | resolver | summarizer`; the model id comes from `Settings.models[role]`.
- `LLMResponse`: `stop_reason`, `text`, `tool_uses: list[ToolUse(id, name, input)]`, `content` (the assistant blocks exactly as returned; append them to the history unchanged), `usage: Usage` (cost computed from `data/pricing.json`).
- `AnthropicLLM(settings)`: SDK retries are off (`max_retries=0`); the wrapper retries up to 3 attempts (1 s, 2 s) on rate limit, connection errors, 5xx and 529. Errors: `LLMUnavailable` (retries exhausted), `LLMBudgetExhausted` (HTTP 400 "usage limits"), `LLMRequestError` (other 4xx and missing key; never echoes request details).
- Unknown model in the pricing file gives cost 0.0 plus one stderr warning.

## Tests without the API (`tests/fakes.py`)
- `FakeLLM(script)`: a list of `LLMResponse` objects (or exceptions to raise) played back in order; records deep copies of every call in `.calls`; fails loudly if the script runs out.
- Build responses with `text_response(text, stop_reason=...)` and `tool_use_response([(name, args), ...], text="")`. For the classifier and resolver on Days 6 and 8, script a forced tool call with `tool_use_response([("classify_ticket", {...})])`.
- `FakeHub(responses)`: same `call` / `tool_defs` surface as `McpHub`; canned envelopes `user_ok`, `access_ok`, `kb_ok`, `resource_ok`, `error_envelope(code, retryable)`; `.calls` logs `(name, args)`.

## MCP hub (`src/mcp_hub.py`)
- `async with McpHub.start(settings) as hub:` in ONE task (do not use a pytest fixture). `hub.tool_names`, `hub.tool_defs(allowed)` (sorted Anthropic tool definitions), `await hub.call(name, args)` returns the envelope, retrying `retryable` errors twice (0.5 s, 1 s); 10 s timeout per call, 20 s startup timeout. `READ_ONLY_TOOLS` is for the model, `WRITE_TOOLS` for the coordinator's commit step only (ADR-014).
- **Caveat:** MCP child processes inherit only a safe environment list, not your shell. `FAULT_INJECT` is therefore passed explicitly from `settings.fault_inject`, and the API key never reaches the servers.

## Diagnostics loop (`src/agents/diagnostics.py`)
- `await diagnose(llm, hub, ticket, classification, thread_summary, settings, allowed_tools=READ_ONLY_TOOLS, counters=Counters()) -> (Facts, Usage)`.
- Loop: at most `max_loop_iterations` model calls, `max_tool_calls` tool calls; tools of one turn run in parallel (`asyncio.gather`, kept) and all results return in ONE user message. `max_tokens`, `refusal` or an empty tool turn end the loop with the gap `diagnostics stopped: <reason>`.
- `LimitExceeded(kind, usage=, partial_facts=)` for `iterations` / `tool_calls`; `LLMUnavailable` etc. propagate. The Day 8 coordinator must catch both and still report usage and facts.
- Facts come only from tool results (`build_facts`): user = first valid `get_user`; access = most sensitive `check_access`; KB matches merged, de-duplicated by best score. Gaps: `required:<tool>:<code|not_called>` for required tools (G7) without a success, `<tool>:<code>` for other failures, `INVALID_DATA` for malformed data. Model text never fills Facts.
- Untrusted ticket text is rendered only by `render_ticket` (`<ticket trust="untrusted">`, HTML-escaped). `pre_tool_check` is an allow-list stub (a disallowed tool returns `FORBIDDEN` to the model and never reaches the hub); Day 7 completes it.

## Differences from the blueprint
1. Extra gap `required:<tool>:not_called` (blueprint covered only failed calls).
2. Several `check_access` calls: the most sensitive resource wins.
3. `LimitExceeded` carries `usage` and `partial_facts`.
4. `pytest` skips tests marked `live` by default (`pytest -m live` runs them); none exist yet. The live check is `scripts/smoke_diagnose.py`.

## Start Day 6 with
`git checkout main`, `git pull`, `git checkout -b day-06-classifier`. Day 6: classifier (forced tool call), prompt framing, injection pre-check and `detect_security_terms`. Use `FakeLLM` for tests; run live only through a smoke script.
