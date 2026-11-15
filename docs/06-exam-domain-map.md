# 06 - CCAR-F Domain Map

This maps the five CCAR-F exam domains to concrete evidence in the project. The weights below come from public summaries of the exam guide; **always check them against the official Exam Guide on the Anthropic Partner Academy certifications page** and update this file if they differ.

| Domain | Weight (public summaries) |
|--------|---------------------------|
| Agentic Architecture & Orchestration | 27% |
| Claude Code Configuration & Workflows | 20% |
| Prompt Engineering & Structured Output | 20% |
| Tool Design & MCP Integration | 18% |
| Context Management & Reliability | 15% |

## 1. Evidence table

| Domain | What the capstone demonstrates | Where | Day |
|--------|-------------------------------|-------|-----|
| Agentic Architecture | Explicit loop with `stop_reason` handling; coordinator and subagents; isolated context; iteration cap; escalation and human handoff; code-enforced guardrails | `src/coordinator.py`, `src/agents/`, `src/guardrails.py`, ADR-002/004/006 | 3-8 |
| Claude Code Configuration | `CLAUDE.md`, custom commands, hook that runs tests/lint, project-level MCP registration | `CLAUDE.md`, `.claude/`, `.mcp.json` | 1, 10-11 |
| Prompt Engineering | Few-shot examples, explicit categorical criteria, forced-tool structured output, validation-retry loop, untrusted-input framing | `src/agents/classifier.py`, `src/schemas.py`, ADR-005 | 5-7 |
| Tool Design & MCP | Two MCP servers, precise tool descriptions, uniform error contract with `retryable`, argument validation | `mcp_servers/`, `02-architecture.md` section 6 | 2-5 |
| Context Management | Static-prefix caching, per-ticket token budget, facts bundle instead of transcripts, thread summarization, cost reporting | `src/context.py`, audit log, eval report | 8-10 |

## 2. Self-check questions per domain

Use these as exam revision *and* as a review of your own code. If you cannot answer one from your own project, find the gap.

### Agentic Architecture
- What are the possible `stop_reason` values and how does each one change the loop?
- When is a hard-coded rule better than a prompt instruction? Which rules in this project use that?
- What gets lost when a subagent has isolated context, and how do you pass it on?
- What triggers escalation, and what does the human receive?

### Claude Code Configuration
- What belongs in `CLAUDE.md` versus a command versus a hook?
- Which of your rules must *always* happen (hook) versus *should usually* happen (instruction)?
- How do project-level and user-level configuration differ?

### Prompt Engineering
- When do few-shot examples help more than extra instructions?
- Why use a forced tool call instead of "respond in JSON"?
- Schema-valid output can still be wrong. What catches that?
- How do you keep untrusted ticket text from acting as instructions?

### Tool Design & MCP
- What should a good tool description contain?
- Why return structured errors with `retryable`?
- What is the difference between an MCP tool, resource and prompt, and which fit this project?
- How would you limit what a tool can do (least privilege)?

### Context Management
- Why put static content first in the prompt?
- What do you pass between steps: transcript or summary, and why?
- How do you detect and handle a conversation that is too large?
- Which information must survive summarization?

## 3. Trade-offs to be able to discuss (interview and exam)

1. Single agent vs coordinator + subagents (cost, complexity, testability).
2. Prompt rules vs code rules (flexibility vs guarantees).
3. Smaller model for classification vs one model everywhere (cost vs consistency).
4. Retry on validation failure vs fail fast (success rate vs latency/cost).
5. Escalate early vs try harder (risk vs automation rate).
6. Rich tool descriptions vs short ones (accuracy vs tokens).
