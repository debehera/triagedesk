# 08 - Project Plan

> **Superseded by `docs/09-implementation-blueprint.md`** (Days 2-14). Kept for history only.

14 working days. Today is **Day 1**. Each day ends with a commit and an updated decision log if anything changed.

## Day 1 - Scope, docs, setup (today)

- [ ] Read `00-scope.md`; adjust anything you disagree with and freeze it.
- [ ] Read `01-requirements.md` and `02-architecture.md`; note questions in `04-decision-log.md` open questions.
- [ ] Copy this folder's contents into your git repo (see the README of the bundle for exact steps).
- [ ] Create the venv, install dependencies, create `.env` with your API key.
- [ ] Run the verification commands in `07-dev-setup.md` section 6.
- [ ] Run the MCP hello-world exercise (`03-mcp-primer.md`, steps A-C).
- [ ] Commit on branch `day-01-scaffold`.

Exit criteria: imports succeed, the hello client lists and calls tools, docs are committed.

## Day 2 - MCP foundations and mock data
- Finish the primer (steps D, E). Read the tool-design checklist.
- Design the mock data: about 15 users, 10 resources with sensitivity levels, 12 KB articles.
- Write `schemas.py` (Ticket, Classification, Facts, Resolution, Outcome) with unit tests.

## Day 3 - Directory MCP server
- Implement `get_user` and `check_access` with the error contract.
- Unit-test the tool functions directly (valid, invalid, missing).
- Write precise tool descriptions.

## Day 4 - ITSM MCP server
- Implement `search_kb`, `get_ticket`, `update_ticket`, `add_comment`.
- Resolve open question Q3 (keyword search only).

## Day 5 - MCP client wrapper and diagnostics loop
- `mcp_client.py`: start servers, list tools, convert to API tool definitions, call tools.
- First explicit agent loop with `stop_reason` handling and iteration cap.
- Add project `.mcp.json`. Resolve Q1.

## Day 6 - Classifier
- Forced-tool-call classification with Pydantic validation and retry.
- Few-shot examples and category criteria.
- CLI that classifies one ticket.

## Day 7 - Resolver and coordinator
- Resolver subagent (requester steps and handoff summary).
- Coordinator wiring: validate, classify, diagnose, resolve, commit.

## Day 8 - Guardrails and context management
- Implement G1-G7, pre-tool and post-output checks, with table-driven unit tests.
- Token budget, thread summarization (resolve Q2), prompt-cache layout.
- Prompt-injection framing.

## Day 9 - Audit, observability, hardening
- Audit log with redaction and cost tracking.
- Failure-injection tests. Resolve Q4.

## Day 10 - Evals
- Finalize `tickets.jsonl` (43+ tickets, dev/holdout split) and the runner.
- First full eval run; read every failure.

## Day 11 - Iterate and Claude Code setup
- Fix the top failure causes (prompt, tool description, or code), re-run dev split.
- `CLAUDE.md`, commands `/run-evals` and `/triage-sample`, test/lint hook.

## Day 12 - Holdout run and traceability
- Run the holdout split once; record results.
- Requirement-to-evidence table.

## Day 13 - README and demo
- README: problem, architecture diagram, quickstart, metrics, design decisions summary, limitations.
- Record a 2-minute demo.

## Day 14 - Polish and publish
- Clean history, tag `v1.0`, check the README quickstart on a fresh clone.
- Add the project and the CCAR-F credential to resume and LinkedIn; write 3 interview stories (see below).

## Buffer rules
- If a day slips, cut stretch items (FR-24, FR-52, FR-63, web demo), never the evals or guardrails.
- Any scope change gets an ADR entry.

## Interview stories to prepare
1. A guardrail that overrode the model and why that was right.
2. An eval failure you found, diagnosed and fixed.
3. A trade-off you made (cost vs quality, autonomy vs safety) with numbers.
