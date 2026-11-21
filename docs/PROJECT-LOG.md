# TriageDesk - Project Log

One entry per working day. Hours are filled in by the builder; everything else is a factual record. Newest entry last.

| Day | Date | Hours (actual) | Theme | Status |
|-----|------|----------------|-------|--------|
| 1 | 2026-11-14 | 2 | Scope, PRD, blueprint, dev setup | Done |
| 2 | 2026-11-15 | 2 | System design, contracts, mock data, config | Done once the manual close-out steps below are finished |
| 3 | 2026-11-15 | 1 | Loaders + Directory MCP server | Done |
| 4 | 2026-11-16 | 2 | ITSM MCP server | Done |
| 5 | 2026-11-17 | 2 | LLM wrapper, MCP hub, diagnostics loop | Done |
| 6 | 2026-11-18 | 1 | Classifier, prompt framing, injection pre-check | Done |
| 7 | 2026-11-21 | 2 | Guardrails G1-G7, pre-tool check, secret scan | Done |
---

## Day 1 - Scope, requirements, blueprint

- Chose the project (TriageDesk), interviewed for scope, wrote the PRD and the 14-day Implementation Blueprint.
- Decisions: hosted demo; keep all PRD items; Day 10 bar = metrics + live link; 2-3 h/day over 14 days; Render or Railway; pre-set samples + rate limit; single page + trace view.
- Delivered Day 1 docs (`docs/00`-`08`), README, CLAUDE.md, requirements, hello MCP server and client (verified with `mcp` 1.x; pinned `<2`).

## Day 2 - System design, contracts, mock data, config

**Goal:** design the system well enough that Day 3 starts building at once.

**Done**
- GitHub repository `triagedesk` created and cloned; Git identity set.
- Design set: `ARCHITECTURE.md`, `SCHEMA.md`, `API.md`, `UI-WIREFRAMES.md`, `PROJECT-STRUCTURE.md`.
- Declarative code: `schemas.py`, `config.py`, 5 data files, `.env.example`, `.gitattributes`, requirements; 62 offline tests green, Ruff clean.
- Two spec bugs found and fixed before any logic existed: CR-1 (G4 vs G2 conflict) and CR-2 (code-side `security_terms`), both approved.
- Blueprint revised to 1.1; PRD revised to 1.1 (FR-15); ADR-012..021 recorded; Day 1 docs bannered.

**Decisions:** ADR-019, ADR-020, ADR-021 (see decision log). Pitch deck skipped by choice (none existed).

**Deviations from the Blueprint:** loaders (`src/data.py`) moved to Day 3 step 1b (+0.25 h); Day 2 ran longer than 2.5 h because of the design documents.

**Manual close-out (builder):** Console spend limit; confirm model ids; commit and push; fill in hours above.

**Risks carried forward:** Days 5, 8 and 12 are likely longer than 3 h; Docker Desktop on Windows (install early on Day 12); free-tier cold starts on Render.

**Next:** Day 3 - loaders and the Directory MCP server.

## Day 3 - Loaders and Directory MCP server

**Done**
- `src/data.py` loaders with typed models and `is_eligible`.
- Directory MCP server (`get_user`, `find_resource`, `check_access`) split into pure logic and a thin FastMCP wrapper; shared helpers (envelope, ID validation, fault injection, catch-all guard) in `mcp_servers/common.py`.
- 126 offline tests, including a real stdio round trip and fault-injection tests; Ruff clean. Verified in the MCP Inspector.

**Deviations:** `.mcp.json` deferred to Day 11; `@tool_guard` decorator added; stricter ID validation (see `docs/handoff/day-03.md`).

**Next:** Day 4 - ITSM MCP server.

## Day 4 - ITSM MCP server

**Done**
- `search_kb` (deterministic keyword scoring), `get_ticket`, `update_ticket` and `add_comment` (idempotent writes, capped in-memory store) with six seed tickets; FastMCP wrapper `itsm_server.py`.
- 198 offline tests: retrieval quality for all 12 KB articles plus 11 symptom queries, validation, idempotency, stdio round trip, fault injection. Ruff clean. Verified in the MCP Inspector.

**Deviations:** the category filter only boosts articles that already match (a category alone no longer creates a match); `.mcp.json` still deferred to Day 11 (see `docs/handoff/day-04.md`).

**Next:** Day 5 - LLM wrapper, MCP hub and the diagnostics loop. Needs an API key, credits and a Console spend limit.

## Day 5 
Built the LLM wrapper (retries, cost), the MCP hub, the diagnostics loop and the fakes; 284 tests.
First live run: 2 model calls, 4,752 input and 108 output tokens, $0.0106.
Set up $5 credits, a $10 monthly limit and the API key.

## Day 6
Built the classifier, the injection and security-term detectors, the classify CLI, 19 labelled eval tickets and a classify-only runner.
Dev run: 100% category accuracy and 100% severity within ±1 on 12 tickets; holdout untouched. 364 tests.
Prompt cache confirmed working (about 2,350 tokens).

## Day 7
Built guardrail rules G1–G7 with a property test over 13,824 combinations that guardrails never relax an outcome.
Built the full pre-tool check (requester-only lookups) and the secret scan.
Added eval tickets EV-020 to EV-033, 33 in total.
Live check on EV-024 showed the restricted facts and the G2 hit, for $0.0169.
490 tests.