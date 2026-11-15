# 04 - Decision Log (ADRs)

Each entry records a decision, the alternatives considered, and the trade-off. The CCAR-F exam is about trade-off decisions, so this file is the most important document for a reviewer. Add an entry whenever scope, architecture or tooling changes.

Format: **Context -> Options -> Decision -> Consequences**. Status: Proposed / Accepted / Superseded.

---

## ADR-001 - Python 3.11+ with Pydantic v2
- **Status:** Accepted (Day 1)
- **Context:** Python is the target language; structured outputs need strong validation.
- **Options:** dataclasses + manual validation; Pydantic v2.
- **Decision:** Pydantic v2 for all schemas.
- **Consequences:** Free JSON-schema generation for tool definitions; validation errors can be fed back to the model for retries. Adds one dependency.

## ADR-002 - Hand-written agent loop on the Anthropic SDK for the coordinator
- **Status:** Accepted (Day 1), revisit Day 9
- **Context:** The exam stresses understanding the agentic loop (call, inspect `stop_reason`, run tools, append results, repeat). A framework hides this.
- **Options:** (a) Claude Agent SDK for everything; (b) plain `anthropic` SDK with an explicit loop; (c) a third-party agent framework.
- **Decision:** (b) for the coordinator and diagnostics loop, so control flow, limits and guardrail hooks are explicit and testable.
- **Consequences:** More code to write and test, full control over limits and hooks. Agent SDK remains an option for a stretch comparison (document the difference in the README if tried).

## ADR-003 - MCP servers over stdio, built with the Python MCP SDK
- **Status:** Accepted (Day 1)
- **Context:** Tools should be reusable and discoverable by both this app and Claude Code. Author is new to MCP.
- **Options:** Plain Python functions as tools; MCP over stdio; MCP over HTTP.
- **Decision:** MCP over stdio using the SDK's high-level server API. Start with a hello-world server (Day 1-2) before real ones.
- **Consequences:** Real MCP learning and portfolio value; slightly more setup than plain functions. HTTP transport is out of scope (no remote deployment).

## ADR-004 - Policy enforced in code, not only in prompts
- **Status:** Accepted (Day 1)
- **Context:** Ticket text is untrusted and a model can be persuaded; some rules (security incidents, privileged access) must never be broken.
- **Options:** Prompt-only rules; code-only rules; both.
- **Decision:** Rules live in `guardrails.py` and are applied after the model proposes an outcome. Prompts describe the policy for helpfulness, but code is authoritative. Guardrails can only downgrade (more cautious), never upgrade an outcome.
- **Consequences:** Deterministic, unit-testable policy; the model sometimes does work that is later overridden, an acceptable cost.

## ADR-005 - Structured output via forced tool call plus Pydantic validation
- **Status:** Accepted (Day 1)
- **Context:** Classification must be machine-readable and reliable.
- **Options:** Ask for JSON in free text and parse; forced tool call with an input schema; rely only on prompt wording.
- **Decision:** Define a `submit_classification` tool whose input schema comes from the Pydantic model, force it with tool choice, then validate with Pydantic. On validation error, retry with the error text (max 2).
- **Consequences:** Much higher schema compliance than free-text JSON. Schema validity does not guarantee semantic correctness (a valid but wrong category is still possible), which is why evals exist.

## ADR-006 - Separate subagents with isolated context instead of one big agent
- **Status:** Accepted (Day 1)
- **Context:** One agent holding everything grows its context quickly and is hard to test.
- **Options:** Single agent with all tools; coordinator plus narrow subagents.
- **Decision:** Coordinator plus three subagents (classifier, diagnostics, resolver). Subagents receive only the information they need; the coordinator passes explicit structured handoffs, not raw transcripts.
- **Consequences:** Smaller prompts, individually testable, cheaper models possible for easy steps. Cost: more API calls and more handoff code. Subagents do not share memory automatically, so every fact needed downstream must be passed explicitly.

## ADR-007 - Mock data in local JSON files
- **Status:** Accepted (Day 1)
- **Context:** Real ITSM/directory integration is out of scope.
- **Options:** JSON files; SQLite; real sandbox of an ITSM product.
- **Decision:** JSON files under `data/`, loaded by the MCP servers.
- **Consequences:** Easy to inspect and diff; no migrations. Concurrency and persistence are simplistic, which is fine for a demo.

## ADR-008 - Append-only JSONL audit log
- **Status:** Accepted (Day 1)
- **Context:** Need traceability of every decision and cost.
- **Options:** Plain logging; JSONL file; database.
- **Decision:** One JSON line per ticket in `logs/audit.jsonl`, with PII redaction.
- **Consequences:** Trivial to parse for the eval report and for the README metrics.

## ADR-009 - Models configured per role through environment variables
- **Status:** Accepted (Day 1)
- **Context:** Cost and quality differ by step; model names change over time.
- **Options:** Single hard-coded model; per-role env configuration.
- **Decision:** `MODEL_CLASSIFIER`, `MODEL_DIAGNOSTICS`, `MODEL_RESOLVER`, each with a default in `.env.example`.
- **Consequences:** Easy cost/quality experiments and a configuration comparison in evals. Must record the models used in every eval report.

## ADR-010 - Offline unit tests with a mocked model client; evals call the API
- **Status:** Accepted (Day 1)
- **Context:** Tests must be fast, free and deterministic; model quality must still be measured.
- **Decision:** `pytest` suite uses a fake client for the loop, guardrails and schemas. The eval runner is the only component that calls the real API.
- **Consequences:** CI-friendly unit tests; evals are run deliberately and their reports are committed.

## ADR-011 - Pin the MCP Python SDK to 1.x (`mcp<2`)
- **Status:** Accepted (Day 1)
- **Context:** On Day 1 a fresh install pulled mcp 2.x, which renamed `FastMCP` to `MCPServer` and changed other APIs; the hello-world server failed to import.
- **Options:** Pin `mcp<2` and keep the documented 1.x API; migrate to 2.x now.
- **Decision:** Pin `mcp[cli]>=1.2,<2`. Revisit migration after v1.0 of the capstone if time allows.
- **Consequences:** Stable, tested learning path; some newer SDK features unavailable. Migration guide: py.sdk.modelcontextprotocol.io/v2/migration.

---

## ADR-012 - FastAPI backend plus one static page, no front-end build
- **Status:** Accepted (Day 2)
- **Context:** A hosted demo with a trace view is in scope (PRD FR-80..FR-91); the interesting engineering is the agent.
- **Options:** React/Vite; Streamlit/Gradio; FastAPI + static HTML/JS.
- **Decision:** FastAPI serving one static page; DOM built with `textContent` only; CSP `default-src 'self'`.
- **Consequences:** No JS toolchain and a small attack surface; plain DOM code and less visual polish.

## ADR-013 - Directory server gets a third tool, `find_resource`
- **Status:** Accepted (Day 2)
- **Context:** Tickets say "the finance share", not `r-05`.
- **Options:** Let the model guess ids; add alias matching to `check_access`; separate lookup tool.
- **Decision:** Separate `find_resource` tool returning up to 3 candidates with sensitivity.
- **Consequences:** Name resolution is deterministic and testable; one more tool description to get right.

## ADR-014 - Diagnostics uses read-only tools only
- **Status:** Accepted (Day 2)
- **Context:** Ticket text is untrusted and could try to trigger writes.
- **Options:** Give all tools to the model; give read tools only and let the coordinator write.
- **Decision:** `update_ticket` and `add_comment` are called only by the coordinator's commit step; the model never sees them.
- **Consequences:** Least privilege; slightly more coordinator code.

## ADR-015 - Facts bundle assembled by code
- **Status:** Accepted (Day 2)
- **Context:** A model summarising tool output could misreport it.
- **Decision:** Code builds `Facts` from recorded tool results; the model only reads it.
- **Consequences:** Guardrails and audit rely on facts that cannot be hallucinated.

## ADR-016 - Narrow `LLMClient` interface with real and fake implementations
- **Status:** Accepted (Day 2)
- **Context:** Offline, deterministic tests; one place for retries, usage and cost.
- **Decision:** `LLMClient.create(...) -> LLMResponse` implemented by `AnthropicLLM` and `FakeLLM`.
- **Consequences:** Unit tests never call the API; a thin abstraction to maintain.

## ADR-017 - One MCP hub per process, started at startup
- **Status:** Accepted (Day 2)
- **Context:** Starting stdio servers per request adds about a second and leaks processes.
- **Decision:** `McpHub` starts both servers once (CLI run, eval run, web lifespan); tool names unique across servers.
- **Consequences:** Faster requests; lifecycle must be handled carefully in tests and on shutdown.

## ADR-018 - Render (Docker), in-memory limits, single instance
- **Status:** Accepted (Day 2)
- **Context:** Free hosting that can run child processes; public demo needs abuse control.
- **Options:** Serverless (cannot hold stdio children); Railway; Hugging Face Spaces; Render.
- **Decision:** Render free web service from a Dockerfile, one Uvicorn worker, in-memory per-IP rate limit and daily cap, plus a Console spend limit.
- **Consequences:** Limits reset on restart and do not scale horizontally; acceptable for a demo. The service sleeps when idle.

## ADR-019 - CR-1: G4 access clause fires only when `facts.access is None`
- **Status:** Accepted (Day 2, approved by the builder)
- **Context:** Blueprint B9 rule G4 escalated an AUTO access request unless access was standard and eligible. With G2 also firing, a restricted or ineligible request wrongly proposed as AUTO ended ESCALATED, contradicting PRD US-2 (PENDING_APPROVAL regardless of model opinion). Reproduced by running the rules as written.
- **Options:** Leave as is and change the tests and PRD; remove the access clause; narrow it.
- **Decision:** Narrow it: G4 fires for access requests only when `check_access` produced no result. G2 alone handles restricted, privileged and ineligible access.
- **Consequences:** US-2 holds even if the model proposes AUTO; a missing `check_access` result still escalates. Day 7 and Day 8 tests updated.

## ADR-020 - CR-2: code-side `security_terms` flag extends G1
- **Status:** Accepted (Day 2, approved by the builder)
- **Context:** G1 depended only on the model labelling a ticket `security_incident` or P1. A mislabelled security ticket with a KB match (EV-033 pattern) could be auto-resolved.
- **Options:** Rely on prompt quality; add a second model check; add a deterministic keyword detector.
- **Decision:** `detect_security_terms` sets `RiskFlag.SECURITY_TERMS` in code; G1 also fires on it (PRD FR-15).
- **Consequences:** Defence in depth with no model cost. False positives only escalate (safe); false negatives are tracked through the eval set.

## ADR-021 - LF line endings and a Windows-first developer environment
- **Status:** Accepted (Day 2)
- **Context:** The builder uses Windows, VS Code and PowerShell; the deploy target is Linux.
- **Decision:** `.gitattributes` with `* text=auto eol=lf`; no OS-specific paths in committed config; PowerShell equivalents documented in Blueprint Appendix I.
- **Consequences:** No CRLF diffs; some blueprint commands need translating.

## Open questions (resolve by the listed day)

| # | Question | Resolve by |
|---|----------|-----------|
| Q1 | Parallel tool calls: allow them in the diagnostics loop or keep sequential for simplicity? | Day 5 |
| Q2 | Summarize long threads with a cheap model call or truncate? | Day 8 |
| Q3 | Keyword KB search only, or add embeddings? Default: keyword only. | Day 4 |
| Q4 | Include an Agent SDK comparison as a stretch goal? | Day 9 |

## Template for new entries

```markdown
## ADR-0NN - Title
- **Status:** Proposed | Accepted | Superseded by ADR-0MM
- **Context:**
- **Options:**
- **Decision:**
- **Consequences:**
```
