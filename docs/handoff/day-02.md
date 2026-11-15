# Handoff: Day 2 -> Day 3

## State at the end of Day 2
- Repo `triagedesk` (GitHub, branch `main`). Windows + VS Code + PowerShell. Python 3.11+.
- Design set in `docs/`: ARCHITECTURE, SCHEMA, API, UI-WIREFRAMES, PROJECT-STRUCTURE, PROJECT-LOG. Blueprint rev 1.1, PRD rev 1.1.
- Code: `src/schemas.py`, `src/config.py`, `data/{users,resources,access,kb,pricing}.json`, tests (62 passing), `.env.example`, `.gitattributes`.
- NOT built: `src/data.py` (loaders), any MCP server beyond the Day 1 hello example, agents, guardrails, web.

## Differences from the blueprint as originally written
1. Loaders moved from Day 2 to Day 3 step 1b (`src/data.py`, `tests/test_data.py`).
2. `RiskFlag.SECURITY_TERMS` added to `schemas.py` (CR-2). `detect_security_terms` is a Day 6 task.
3. G1 and G4 changed (CR-1, CR-2); see B9 and ARCHITECTURE section 7.
4. API list endpoints return objects (`{"samples": [...]}`, `{"requesters": [...]}`); `NOT_FOUND` error code added (API.md C-1..C-6).
5. Day 5: spend-limit exhaustion is not retried (`LLMBudgetExhausted`).
6. `.vscode/settings.json` has no interpreter path; select the venv in VS Code.

## Models and pricing
Defaults in `src/config.py`: classifier and summarizer `claude-haiku-5-5`; diagnostics and resolver `claude-sonnet-5-5`. Prices in `data/pricing.json` come from the pricing documentation as of Day 2 (re-verify before Day 10 cost claims).

## Start Day 3 with
`git checkout -b day-03-directory-server`, then step 1b (loaders), then the Directory server per the Day 3 section and `docs/API.md` Part B.

## Open items for the builder
Console spend limit set? Commit and push done? Hours logged in `docs/PROJECT-LOG.md`?
