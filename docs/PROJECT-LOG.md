# TriageDesk - Project Log

One entry per working day. Hours are filled in by the builder; everything else is a factual record. Newest entry last.

| Day | Date | Hours (actual) | Theme | Status |
|-----|------|----------------|-------|--------|
| 1 | (fill in) | (fill in) | Scope, PRD, blueprint, dev setup | Done |
| 2 | 2026-11-15 | (fill in) | System design, contracts, mock data, config | Done once the manual close-out steps below are finished |

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
