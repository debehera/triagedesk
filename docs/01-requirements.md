# 01 - Requirements

Priority uses MoSCoW: **M**ust, **S**hould, **C**ould. IDs are used in tests, commits and the decision log so every requirement is traceable.

## 1. Functional requirements

### 1.1 Ticket intake

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-1 | M | Accept a ticket as JSON (`id`, `subject`, `body`, `requester_id`, optional `thread`) from a file, stdin or the batch runner. |
| FR-2 | M | Validate input with a Pydantic model; reject or flag malformed tickets with a clear error and a safe outcome (ESCALATED), never an unhandled exception. |
| FR-3 | S | Truncate or summarize oversized ticket bodies/threads according to the context policy (FR-30). |

### 1.2 Classification

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-10 | M | Produce a `Classification` object: `category`, `severity`, `confidence` (0-1), `affected_system`, `summary`, `risk_flags`. |
| FR-11 | M | Output must be schema-validated; on validation failure retry with the validation error fed back, at most 2 retries, then ESCALATED. |
| FR-12 | M | Use few-shot examples for ambiguous categories. |
| FR-13 | M | Ticket text is treated as untrusted input: instructions inside it must not alter system behaviour. |

### 1.3 Enrichment (tool use)

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-20 | M | Look up the requester (`get_user`) before any access-related decision. |
| FR-21 | M | Search the knowledge base (`search_kb`) for a matching fix before drafting a resolution. |
| FR-22 | M | For access requests, check current rights (`check_access`) and resource sensitivity. |
| FR-23 | M | Tool errors use a uniform error contract (`ok`, `error.code`, `error.message`, `error.retryable`) and the agent handles `retryable` vs non-retryable differently. |
| FR-24 | S | Tool calls with no data dependency between them may run in parallel. |

### 1.4 Resolution and escalation

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-30 | M | Decide an outcome: AUTO_RESOLVED, PENDING_APPROVAL or ESCALATED, following the policy table in `02-architecture.md`. |
| FR-31 | M | For AUTO_RESOLVED, draft requester-facing steps grounded in a KB article (cite article id). No KB match means no auto-resolve. |
| FR-32 | M | For ESCALATED / PENDING_APPROVAL, produce a handoff summary: what was asked, what was checked, what is uncertain, recommended next step. |
| FR-33 | M | Update the mock ticket through `update_ticket` with status and an internal note. |
| FR-34 | M | Escalate when `confidence` is below the configured threshold (default 0.70). |

### 1.5 Guardrails (enforced in code)

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-40 | M | `security_incident` tickets and any P1 ticket are always escalated; the model cannot override this. |
| FR-41 | M | Access to resources marked `restricted` or `privileged` always requires human approval. |
| FR-42 | M | The agent never outputs or requests passwords, MFA codes or secrets; outputs are scanned and blocked if they match. |
| FR-43 | M | Maximum agent-loop iterations (default 8) and maximum tool calls per ticket (default 10); exceeding either escalates. |
| FR-44 | M | Every guardrail decision is logged with its rule id. |
| FR-45 | S | A pre-tool hook validates tool arguments against an allow-list before the call is made. |

### 1.6 Observability and audit

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-50 | M | Append one JSON line per ticket to `logs/audit.jsonl`: input hash, classification, tools called, guardrail hits, outcome, tokens, latency. |
| FR-51 | M | Record token usage (input, output, cached) and estimated cost per ticket. |
| FR-52 | S | Redact obvious PII (email addresses, phone numbers) in logs. |

### 1.7 Evaluation

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-60 | M | A labelled eval set of at least 40 tickets, covering every category, ambiguous tickets, multi-issue tickets, adversarial tickets and prompt-injection tickets. |
| FR-61 | M | An eval runner that reports category accuracy, severity accuracy, escalation recall on high-risk tickets, guardrail results and cost. |
| FR-62 | S | A regression threshold: the eval command exits non-zero if key metrics drop below target. |
| FR-63 | C | Compare two configurations (e.g. different models for classification) in one report. |

### 1.8 Claude Code project setup

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-70 | M | `CLAUDE.md` documenting project conventions, commands and architecture rules. |
| FR-71 | M | At least two custom commands in `.claude/commands/` (e.g. `/run-evals`, `/triage-sample`). |
| FR-72 | S | A hook that runs lint/tests after code edits. |
| FR-73 | S | The project MCP servers registered through a project-level MCP config. |

## 2. Non-functional requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Reliability | No unhandled exception from any input in the eval and fuzz sets. |
| NFR-2 | Determinism | Policy decisions (guardrails) are deterministic given the same classification and tool results; covered by unit tests without calling the API. |
| NFR-3 | Cost | Per-ticket token budget enforced (default 20k input tokens); cost reported. |
| NFR-4 | Latency | Informational: median under 15 s per ticket with the default models. Not a hard target. |
| NFR-5 | Security | Secrets only through environment variables; `.env` is git-ignored; no real personal data in the repo. |
| NFR-6 | Maintainability | Type hints, Ruff lint clean, small modules; each agent and guardrail independently testable. |
| NFR-7 | Testability | Unit tests run offline with a mocked model client; evals are the only tests that call the API. |
| NFR-8 | Portability | Runs on Windows, macOS and Linux with Python 3.11+. |
| NFR-9 | Documentation | Every architectural decision has an entry in `04-decision-log.md`. |

## 3. Constraints and dependencies

- Python 3.11+, `anthropic` SDK, `mcp` Python SDK, `pydantic` v2, `pytest`, `ruff`.
- An Anthropic API key in `ANTHROPIC_API_KEY`.
- Model names configurable by environment variable (never hard-coded in logic).

## 4. Traceability

Each requirement ID appears in at least one of: a test name, a commit message, or an eval case. The Day 12 task is to generate a requirement-to-evidence table for the README.
