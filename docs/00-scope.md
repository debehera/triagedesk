# 00 - Project Scope

> **Superseded in part by `docs/PRD.md` (v1.0, revision 1.1).** The web demo is now in scope; see PRD sections 3 and 14 for the current scope.

**Project:** TriageDesk - an IT Incident Triage & Resolution Agent built on Claude
**Purpose:** Capstone after the Claude Certified Architect - Foundations (CCAR-F) certification, built as a portfolio piece for IT-industry job applications.
**Language:** Python 3.11+
**Status:** Draft v0.1 (Day 1) - freeze at end of Day 1, change only through the decision log.

---

## 1. Problem statement

IT service desks receive a steady stream of repetitive Level-1 tickets (password resets, VPN problems, access requests, software installs). Humans spend most of their time on classification, lookup and copy-paste responses, while a small number of risky tickets (security incidents, privileged access) need careful human attention.

TriageDesk automates the routine work and **reliably** routes the risky work to people. The point of the project is not "an LLM answers tickets" but "an LLM-based system whose behaviour is predictable, auditable and safe", because that is what the CCAR-F certification is about.

## 2. Goals

| ID | Goal |
|----|------|
| G1 | Classify incoming tickets into a fixed category and severity with structured, validated output. |
| G2 | Enrich each ticket with facts from tools (user record, access rights, knowledge base) instead of guessing. |
| G3 | Auto-resolve low-risk tickets with a documented fix; draft a response for the requester. |
| G4 | Escalate high-risk or low-confidence tickets to a human with a concise handoff summary. |
| G5 | Enforce policy in code (guardrails), so that safety never depends only on prompt wording. |
| G6 | Measure quality with a labelled eval set and publish the numbers in the README. |
| G7 | Demonstrate all five CCAR-F exam domains with traceable evidence in the repo. |

## 3. Non-goals (explicitly out of scope)

- Integration with real ITSM products (ServiceNow, Jira Service Management) or real directories (Active Directory, Entra ID). All systems are **mock** MCP servers backed by local JSON.
- ~~A web front-end.~~ **Changed on Day 1/2:** a hosted single-page demo with a trace view is now IN scope (PRD FR-80..FR-91). Non-goals are listed in PRD section 3.2.
- Authentication, multi-tenancy, RBAC for the tool itself.
- Model fine-tuning or training.
- Real credential handling. The agent never sets, reveals or stores passwords.
- Voice, chat-channel (Slack/Teams) integrations.

## 4. Users and stakeholders

| Role | Interest |
|------|----------|
| Requester (employee) | Fast, correct answer or a clear "a human will handle this". |
| L1/L2 service-desk agent | Receives escalations with enough context to act without re-asking. |
| IT manager | Wants metrics: auto-resolution rate, escalation reasons, cost per ticket. |
| Recruiter / hiring manager (the real audience) | Wants evidence of sound design, tests and trade-off thinking. |

## 5. Scope of behaviour

### 5.1 Ticket categories (fixed taxonomy)

`password_reset`, `access_request`, `vpn_network`, `software_install`, `hardware`, `email_calendar`, `security_incident`, `other`

### 5.2 Severity

`P1` (critical / outage / active security threat), `P2` (major impact), `P3` (normal), `P4` (low / informational)

### 5.3 Outcomes

Every ticket ends in exactly one outcome:

1. **AUTO_RESOLVED** - fix is documented in the KB and risk is low; requester gets steps.
2. **PENDING_APPROVAL** - action is legitimate but needs human approval (e.g. access to a restricted resource).
3. **ESCALATED** - needs a human to investigate (security, ambiguity, low confidence, tool failure).

### 5.3.1 Autonomy rule of thumb

The agent may *suggest and explain*. It may never *grant, reset or change* anything in a real system. In this project the "actions" are mock tool calls that update a mock ticket, so the architecture is realistic without real-world risk.

## 6. Success criteria (measurable)

| ID | Metric | Target |
|----|--------|--------|
| S1 | Category accuracy on the labelled eval set (40+ tickets) | >= 90% |
| S2 | Severity within one level of the label | >= 90% |
| S3 | High-risk tickets (security incident, privileged access) escalated or sent for approval | 100% |
| S4 | Policy-violating actions blocked by guardrails in adversarial tests | 100% |
| S5 | Prompt-injection test tickets that do not change agent behaviour | 100% of the injection test set |
| S6 | Malformed or empty input handled without an unhandled exception | 100% |
| S7 | Schema-valid structured output after retry | >= 99% |
| S8 | Average tokens and cost per ticket recorded and reported | Reported (no target; it is a trade-off to discuss) |

Targets are goals, not promises: if results differ, the README reports the real numbers and discusses why.

## 7. Assumptions

- The author has an Anthropic API key and a small budget for development runs.
- Mock data is realistic enough to exercise the design (about 15 users, 12 KB articles, 40+ eval tickets).
- Latency is not a primary requirement (batch/near-real-time is fine).
- English-language tickets only.

## 8. Constraints

- Solo developer, about 14 working days.
- Python only.
- Everything must run locally from the repo with one `.env` file and `pip install -r requirements.txt`.

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Scope creep (web UI, real integrations) | Misses deadline | Non-goals list above; changes only via the decision log |
| First time with MCP | Slow start | Day 1-2 hello-world server and client (see `03-mcp-primer.md`) before building real servers |
| Model output not schema-valid | Pipeline crashes | Forced tool-call schema + Pydantic validation + bounded retry |
| Prompt injection inside ticket text | Unsafe behaviour | Treat ticket body as untrusted data, guardrails in code, injection tests in evals |
| Runaway tool loops or cost | Budget overrun | Max-iterations and max-tool-calls limits, per-ticket token budget |
| API cost during development | Budget overrun | Cheaper model for classification, small eval subset for iteration, cache static prompts |
| Eval set too easy | Misleading numbers | Include ambiguous, multi-issue and adversarial tickets from the start |

## 10. Deliverables

1. Working Python application (CLI + batch runner).
2. Two mock MCP servers (ITSM, directory).
3. Eval set, eval runner and a results report.
4. Claude Code project configuration (`CLAUDE.md`, commands, hooks).
5. Documentation set in `docs/` (this folder).
6. README with architecture diagram, metrics and design-decision summary.
7. Short demo recording (GIF or video) linked from the README.

## 11. Definition of done

- All "must" requirements in `01-requirements.md` implemented and tested.
- Eval run committed with results; targets met or honestly explained.
- README lets a stranger clone, configure and run the demo in under 10 minutes.
- Decision log up to date; every deviation from this scope has an entry.
