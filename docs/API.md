# TriageDesk - API and Interface Specification (v1.0)

| | |
|---|---|
| **Status** | Final for v1.0 (Day 2, revision 1.1). No implementation exists yet; this is the contract Days 3-12 build to |
| **Covers** | (A) public HTTP API, (B) internal MCP tool API, (C) command-line interfaces |
| **Companion docs** | `ARCHITECTURE.md`, `SCHEMA.md`, Blueprint Part B (B2, B3, B12) |
| **Authority** | Blueprint B2/B3/B12 and PRD FR-80..FR-91 win in any conflict; section 6 lists the clarifications this document adds |

---

# Part A - HTTP API (web demo, Day 12)

## 1. Conventions

| Topic | Rule |
|-------|------|
| Base URL | Same origin as the page: `http://localhost:8000` locally, the Render URL when deployed. No CORS |
| Format | JSON in, JSON out, UTF-8. `Content-Type: application/json` on POST |
| Authentication | **None.** The demo is public by design (PRD non-goal). Abuse is limited by rate limit, daily cap, input caps, concurrency limit and timeout. The Anthropic key never leaves the server |
| Versioning | None in v1.0 (paths are `/api/...`) |
| Error body | `{"error": {"code": "<CODE>", "message": "<human readable>"}}` on every non-2xx under `/api/*` |
| Error codes | `INVALID_INPUT`, `RATE_LIMITED`, `DAILY_CAP`, `TIMEOUT`, `INTERNAL`, `NOT_FOUND` |
| Never in a response | Stack traces, exception text, API keys, file paths, raw model output outside `TriageResult` |
| Response headers (all) | `Content-Security-Policy: default-src 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; plus `Cache-Control: no-store` on `/api/*` |
| Request body limit | 16 KB for `POST /api/triage` (HTTP 413, code `INVALID_INPUT`) |
| Logging | Method, path, status, duration, derived client IP hash. **Never** subject or body |

## 2. Endpoint index

| Method | Path | Purpose | Calls the model? | Rate limited? |
|--------|------|---------|------------------|---------------|
| GET | `/` | The single-page UI | No | No |
| GET | `/static/{file}` | `app.js`, `style.css` | No | No |
| GET | `/healthz` | Liveness / platform health check | No | No |
| GET | `/api/samples` | The 8 public sample tickets | No | No |
| GET | `/api/requesters` | Mock users for the requester dropdown | No | No |
| POST | `/api/triage` | Triage one ticket and return the full result with trace | **Yes** | **Yes**, plus daily cap |

That is every endpoint needed for v1.0. There is no login, history, admin or eval endpoint on purpose.

## 3. Endpoint specifications

### 3.1 `GET /`

| | |
|---|---|
| Purpose | Serve `index.html` (UI spec in `UI-WIREFRAMES.md`) |
| Authentication | None |
| Request | None |
| Validation | None |
| Response | `200 text/html` |
| Errors | None expected |

### 3.2 `GET /static/{file}`

| | |
|---|---|
| Purpose | Serve `app.js` and `style.css` (no inline scripts or styles, so the CSP holds) |
| Authentication | None |
| Response | `200` with the file; `404` (plain) for unknown files |
| Notes | Directory listing disabled; path traversal blocked by the static-files handler |

### 3.3 `GET /healthz`

| | |
|---|---|
| Purpose | Health check used by Render and by humans |
| Authentication | None |
| Request | None |
| Response | `200 {"status": "ok"}` |
| Validation / errors | None. Must **not** touch the model or the MCP servers, so a check cannot cost money |

### 3.4 `GET /api/samples`

| | |
|---|---|
| Purpose | Populate the sample picker with the 8 tickets marked `public` in the eval set |
| Authentication | None |
| Request | None |
| Response `200` | `{"samples": [{"id": "EV-001", "subject": "...", "body": "...", "requester_id": "u-101"}, ...]}` - exactly 8 items |
| Validation | None |
| Errors | `500 INTERNAL` if the eval file is unreadable (checked at startup, so unlikely) |
| Security | Built from an allow-list of four fields; **expected labels are never exposed** |

### 3.5 `GET /api/requesters`

| | |
|---|---|
| Purpose | Populate the requester dropdown |
| Authentication | None |
| Request | None |
| Response `200` | `{"requesters": [{"id": "u-101", "name": "Asha Rao", "role": "Software Engineer", "status": "active"}, ...]}` - 15 items, including the disabled `u-115` so visitors can see rule G7 |
| Security | Email, department and manager are not returned |

### 3.6 `POST /api/triage`

| | |
|---|---|
| Purpose | Run the full pipeline on one ticket and return the result with its trace |
| Authentication | None (abuse controls apply) |

**Request body**

```json
{
  "subject": "Need access to the finance share",
  "body": "Hi, I am starting on the quarterly close and need access to the finance shared drive.",
  "requester_id": "u-104"
}
```

| Field | Type | Validation |
|-------|------|------------|
| `subject` | string | Required; 1-200 characters; not blank after trimming |
| `body` | string | Required; 1-2,000 characters; not blank after trimming |
| `requester_id` | string | Required; pattern `^u-\d{3}$`. An id that matches the pattern but does not exist (for example `u-999`) is **valid input**: the pipeline escalates it through guardrail G7 |
| any other field | - | Rejected (`extra = forbid`). In particular there is no `thread` in the public API (FR-86) |

**Order of checks** (the first failure wins; see section 5): body size, JSON and field validation, per-IP rate limit, daily cap, concurrency slot and timeout.

**Success response `200`** - a `TriageResult` (`SCHEMA.md` section 4.1). Illustrative example (trace abridged):

```json
{
  "ticket_id": "WEB-3f9a1c2b",
  "classification": {
    "category": "access_request", "severity": "P3", "confidence": 0.93,
    "affected_system": "Finance Shared Drive",
    "summary": "Requester asks for access to the finance shared drive.",
    "risk_flags": ["privileged_resource"]
  },
  "facts": {
    "user": {"id": "u-104", "name": "Dev Patel", "department": "Finance",
             "role": "Financial Analyst", "manager_id": "u-111", "status": "active"},
    "access": {"user_id": "u-104", "resource_id": "r-05",
               "resource_name": "Finance Shared Drive", "sensitivity": "restricted",
               "has_access": false, "eligible": true},
    "kb_matches": [], "gaps": [],
    "tool_calls": [
      {"name": "get_user", "args": {"user_id": "u-104"}, "ok": true, "error_code": null, "retryable": null, "ms": 5},
      {"name": "find_resource", "args": {"query": "finance share"}, "ok": true, "error_code": null, "retryable": null, "ms": 4},
      {"name": "check_access", "args": {"user_id": "u-104", "resource_id": "r-05"}, "ok": true, "error_code": null, "retryable": null, "ms": 4}
    ]
  },
  "resolution": {
    "proposed_outcome": "PENDING_APPROVAL", "requester_steps": [], "kb_article_id": null,
    "handoff_summary": "Dev Patel (Financial Analyst) requests the Finance Shared Drive, a restricted resource. Role is eligible. Needs manager or owner approval.",
    "confidence": 0.9
  },
  "final_outcome": "PENDING_APPROVAL",
  "reasons": ["G2: access to Finance Shared Drive is restricted -> approval required"],
  "guardrail_hits": [
    {"rule_id": "G2", "message": "restricted resource", "from_outcome": "AUTO_RESOLVED", "to_outcome": "PENDING_APPROVAL"}
  ],
  "usage": {"input_tokens": 13500, "output_tokens": 900, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.03},
  "latency_ms": 14200,
  "trace": [
    {"step": "validate", "detail": {}, "ms": 1},
    {"step": "classify", "detail": {"attempts": 1}, "ms": 1400},
    {"step": "diagnose", "detail": {"iterations": 2}, "ms": 6100},
    {"step": "resolve", "detail": {"attempts": 1}, "ms": 3200},
    {"step": "guardrails", "detail": {"hits": ["G2"]}, "ms": 0},
    {"step": "commit", "detail": {"status": "pending_approval"}, "ms": 12}
  ]
}
```

A processed ticket **always** returns `200`, even when the outcome is `ESCALATED` because of an internal problem (for example `reasons` starting `ERR:classification`). `triage()` never raises (ARCHITECTURE section 4.2).

**Error responses**

| Status | Code | When | Extra |
|--------|------|------|-------|
| 413 | `INVALID_INPUT` | Request body larger than 16 KB | - |
| 422 | `INVALID_INPUT` | Missing, mistyped, too long, blank or unknown field; message names the field | - |
| 429 | `RATE_LIMITED` | More than 5 requests per minute from this IP | `Retry-After: <seconds>` |
| 503 | `DAILY_CAP` | Global cap of 150 runs for the UTC day reached, **or** the Anthropic spend limit is exhausted (`ERR:llm:budget_exhausted`) | `Retry-After: <seconds until 00:00 UTC>` for the daily cap |
| 504 | `TIMEOUT` | Pipeline did not finish within 60 s | - |
| 500 | `INTERNAL` | Unexpected server error; generic message only | - |

Example error:

```json
{"error": {"code": "RATE_LIMITED", "message": "Too many requests. Try again in 41 seconds."}}
```

Unknown paths under `/api/` return `404` with code `NOT_FOUND` in the same shape; wrong methods return `405` with code `INVALID_INPUT`.

## 4. Error catalog and the UI message for each

| Code | HTTP | UI behaviour (copy is defined in `UI-WIREFRAMES.md`) |
|------|------|-------------------------------------------------------|
| `INVALID_INPUT` | 413, 422 | Inline message next to the form; no retry timer |
| `RATE_LIMITED` | 429 | Banner with a countdown from `Retry-After`; button disabled until it ends |
| `DAILY_CAP` | 503 | Banner explaining the demo budget is used up for today; points to the README demo recording |
| `TIMEOUT` | 504 | "This took too long" with a Try again button |
| `INTERNAL` | 500 | Generic error with a Try again button |
| (network failure) | - | "Could not reach the server" (the free host may be waking up; wait about a minute) |

## 5. Request-handling order and limits

```text
POST /api/triage
  1. Body larger than 16 KB            -> 413
  2. JSON / field validation           -> 422
  3. Per-IP sliding window (5/min)     -> 429 + Retry-After
  4. Daily cap (150 per UTC day)       -> 503 DAILY_CAP
  5. Wait for a concurrency slot (2)   -> then run triage() under a 60 s timeout -> 504 on expiry
  6. Return TriageResult               -> 200
```

Cheap rejections come first so that no model call, and no cost, is incurred for bad or excessive requests. The client IP is `request.client.host`, or the first value of `X-Forwarded-For` only when `TRUSTED_PROXY=true`.

## 6. Clarifications this document adds to Blueprint B12 (additive, no conflict)

| # | Clarification | Reason |
|---|---------------|--------|
| C-1 | `GET /api/samples` returns `{"samples": [...]}` and `GET /api/requesters` returns `{"requesters": [...]}` (objects, not bare arrays) | Allows adding fields later without breaking the client |
| C-2 | Error code `NOT_FOUND` for unknown `/api/*` paths | Keeps one error shape for every `/api/*` response |
| C-3 | `extra = forbid` on the request model | Enforces FR-86 (no thread through the public API) |
| C-4 | Spend-limit exhaustion maps to 503 `DAILY_CAP` | Anthropic returns HTTP 400/429 when a spend limit is reached; retrying is pointless and the user needs a clear message |
| C-5 | 16 KB request-body limit (413) | Cheap protection against oversized payloads |
| C-6 | `/api/requesters` includes the disabled user | Lets visitors exercise guardrail G7 |

---

# Part B - Internal tool API (MCP)

Seven tools on two stdio servers. They are called by the **MCP hub** on behalf of the diagnostics agent (read-only tools) and the coordinator's commit step (write tools). They are not network-exposed.

## 7. Tool contract

| Item | Rule |
|------|------|
| Success | `{"ok": true, "data": {...}}` |
| Failure | `{"ok": false, "error": {"code": "...", "message": "...", "retryable": false}}` |
| Codes | `NOT_FOUND`, `INVALID_INPUT`, `TIMEOUT` (retryable), `INTERNAL` (retryable once), `FORBIDDEN` (pre-tool guardrail only, never from a server) |
| Transport | FastMCP over stdio; the dict is serialized to JSON text in `result.content[0].text` and parsed by the hub |
| Authentication | None (child processes of the app). Authorization is the **allow-list** below plus pre-tool argument checks |
| Fault injection | Env `FAULT_INJECT` JSON, e.g. `{"get_user": "TIMEOUT_ONCE"}`; values `TIMEOUT`, `INTERNAL`, `NOT_FOUND`, `TIMEOUT_ONCE` (tests only) |

**Who may call what**

| Tool | Server | Kind | Diagnostics agent | Security / P1 tickets | Commit step |
|------|--------|------|-------------------|-----------------------|-------------|
| `get_user` | directory | read | yes | **yes (only this one)** | - |
| `find_resource` | directory | read | yes | no | - |
| `check_access` | directory | read | yes | no | - |
| `search_kb` | itsm | read | yes | no | - |
| `get_ticket` | itsm | read | yes | no | - |
| `update_ticket` | itsm | **write** | **never** | never | yes |
| `add_comment` | itsm | **write** | **never** | never | yes (AUTO_RESOLVED only) |

Pre-tool check (diagnostics only): tool name in the allowed set; argument keys known; `user_id` equals the ticket's requester; ids match `^u-\d{3}$` / `^r-\d{2}$`; strings at most 200 characters with no control characters; `limit` an integer 1-5. A violation returns `FORBIDDEN` to the model and a `PRE` guardrail hit.

## 8. Tool specifications

### 8.1 `get_user` (directory)

| | |
|---|---|
| Purpose | Look up the requester's role, department and whether the account is active. Always the first call |
| Request | `user_id: string` |
| Validation | Pattern `^u-\d{3}$`, else `INVALID_INPUT` |
| Success `data` | `{id, name, department, role, manager_id, status}` (email is **not** returned) |
| Errors | `NOT_FOUND` (retryable false), `INVALID_INPUT`; injected `TIMEOUT`/`INTERNAL` |

### 8.2 `find_resource` (directory)

| | |
|---|---|
| Purpose | Map words in a ticket ("the finance share", "prod db") to resource ids. Does not check anyone's access |
| Request | `query: string` |
| Validation | 1-100 characters, not blank |
| Scoring | +3 if the query equals an alias; +2 if an alias is contained in the query or the reverse; +1 per shared word of 3+ letters with the resource name; keep score > 0, sort by score then id |
| Success `data` | `{"resources": [{"id", "name", "sensitivity"}]}` - up to 3, best first |
| Errors | `NOT_FOUND` when nothing scores; `INVALID_INPUT` |

### 8.3 `check_access` (directory)

| | |
|---|---|
| Purpose | Does this user hold this resource, how sensitive is it, and may their role request it |
| Request | `user_id: string`, `resource_id: string` |
| Validation | `^u-\d{3}$` and `^r-\d{2}$` |
| Success `data` | `{user_id, resource_id, resource_name, sensitivity, has_access, eligible}`; `eligible = "*" in allowed_roles or role in allowed_roles` |
| Errors | `NOT_FOUND` (unknown user or resource), `INVALID_INPUT` |

### 8.4 `search_kb` (itsm)

| | |
|---|---|
| Purpose | Find knowledge-base articles for a short symptom description. Use before proposing any fix |
| Request | `query: string`, `category: string \| null`, `limit: int = 3` |
| Validation | `query` 1-200 characters; `category` null or a valid `Category`; `limit` 1-5 |
| Scoring | Tokens: lowercase, split on non-alphanumerics, keep 3+ letters, drop stopwords. Score = 2.0 per query token in the title + 1.0 per token in the keywords + 1.5 if the category filter matches; drop scores below 1.0; sort by score then id |
| Success `data` | `{"matches": [{id, title, category, score, steps}]}`. **An empty list is success** (no relevant article), not an error |
| Errors | `INVALID_INPUT` |

### 8.5 `get_ticket` (itsm)

| | |
|---|---|
| Purpose | Fetch a ticket's subject, status and notes |
| Request | `ticket_id: string` |
| Success `data` | `{id, subject, status, notes}` |
| Errors | `NOT_FOUND`, `INVALID_INPUT` |

### 8.6 `update_ticket` (itsm, write)

| | |
|---|---|
| Purpose | Record the final status and an internal note. **Commit step only** |
| Request | `ticket_id: string`, `status: "open" \| "resolved" \| "pending_approval" \| "escalated"`, `note: string` |
| Validation | Status in the enum; note at most 1,000 characters |
| Behaviour | Upsert (unknown ids are created); idempotent for an identical `(ticket_id, status, note)`; at most 1,000 tickets kept |
| Success `data` | `{ticket_id, status}` |
| Errors | `INVALID_INPUT` |
| Status mapping | AUTO_RESOLVED -> `resolved`, PENDING_APPROVAL -> `pending_approval`, ESCALATED -> `escalated` |

### 8.7 `add_comment` (itsm, write)

| | |
|---|---|
| Purpose | Add a requester-visible or internal comment. **Commit step only**, and only for AUTO_RESOLVED (requester steps) |
| Request | `ticket_id: string`, `text: string`, `visibility: "requester" \| "internal"` |
| Validation | Text 1-1,000 characters; visibility in the enum |
| Behaviour | Identical text on the same ticket returns the existing comment id |
| Success `data` | `{ticket_id, comment_id}` with `comment_id = "C-0001"` style |
| Errors | `INVALID_INPUT` |

Tool descriptions (the docstrings the model sees) are written as briefings: what it does, when to use it, when not to, what it returns. They are reviewed like prompts (Blueprint Days 3-4).

---

# Part C - Command-line interfaces

## 9. Application CLI (`python -m src.cli`, Days 6-8)

| Command | Purpose | Options | Exit codes |
|---------|---------|---------|------------|
| `classify <ticket.json>` | Classifier only; prints the `Classification`, attempts, tokens, cost | - | 0 ok, 2 usage or file error |
| `triage <ticket.json>` | Full pipeline on one ticket | `--json` (machine-readable result), `--trace` (print the trace) | 0 ok, 2 usage or file error |
| `batch <tickets.jsonl>` | Many tickets, one line each: id, expected vs actual outcome, category, guardrail ids, cost | `--split dev\|holdout\|all`, `--ids EV-001,EV-003`, `--concurrency 2` | 0 ok, 2 usage error |

Input is raw JSON; malformed tickets are passed through so validation can escalate them.

## 10. Eval runner (`python evals/run_evals.py`, Day 10)

| Option | Default | Meaning |
|--------|---------|---------|
| `--split` | `dev` | `dev`, `holdout` or `all`. **Never** run `holdout` until Day 13 |
| `--ids` | - | Comma-separated ticket ids |
| `--limit` | - | First N tickets |
| `--concurrency` | 2 | Parallel tickets |
| `--max-cost` | - | Abort remaining tickets when estimated spend exceeds this (USD) |
| `--out` | timestamp | Report name in `evals/reports/` |
| `--no-gate` | off | Do not fail on missed targets |

Exit code **1** when a must-target is missed (category < 90%, severity within one level < 90%, outcome < 85%, high-risk recall < 100%, injection resistance < 100%, schema validity < 99%); otherwise 0.

## 11. Other entry points

| Entry point | Purpose |
|-------------|---------|
| `uvicorn src.web.app:app --reload` | Run the web demo locally (Day 12) |
| `python scripts/check.py` | Offline lint + tests (Day 11) |
| `python scripts/cache_check.py` | Measure prompt-cache reads (Day 9, live) |
| `mcp dev mcp_servers/<server>.py` | Inspect an MCP server (needs Node.js; optional) |

---

## 12. Test matrix

| Interface | Tests (offline unless noted) |
|-----------|------------------------------|
| `/healthz` | 200, zero LLM calls |
| `/api/samples` | exactly 8 items, no `expected` field |
| `/api/requesters` | 15 items including the disabled user, no email |
| `POST /api/triage` | valid run returns `TriageResult` with trace; 422 for 2,001-char body, bad id, extra field, blank text; 413 for oversized body; 429 on the 6th request with `Retry-After`; 503 when the daily cap is exhausted and when the spend-limit error is raised; 504 with a tiny timeout; concurrency never exceeds 2; security headers present; no body text in logs |
| Static files | `app.js` contains no `innerHTML` |
| Directory tools | valid, unknown, malformed inputs; the 8 key access pairs; fault injection; stdio round trip |
| ITSM tools | retrieval quality (every article found by its title and a symptom query); no-match is success; writes idempotent; stdio round trip |
| Hub | lists 7 tools; read-only subset has 5; retries retryable errors; unknown tool returns `NOT_FOUND` |
| Pre-tool check | allowed passes; write tool, other user's id, malformed id, unknown argument, `limit=50` blocked |
| CLI / runner | argument parsing offline; live runs are manual |
