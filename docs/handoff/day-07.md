# Handoff: Day 7 -> Day 8

## State at the end of Day 7
- Branch `day-07-guardrails` (merge to `main` after the checks).
- Changed: `src/guardrails.py` (full), `src/safety.py` (secret scan), `src/agents/diagnostics.py` (`blocked` out-parameter), `tests/test_diagnostics.py`, `tests/test_eval_tickets.py`, `evals/tickets.jsonl` (33 tickets), `evals/labels-notes.md`, `scripts/smoke_diagnose.py`.
- New: `tests/test_guardrails.py`, `tests/test_pre_tool_check.py`, `tests/test_secrets.py`.
- 490 tests pass offline; `ruff check .` clean. No `src/coordinator.py` yet (Day 8).

## `apply_guardrails` (src/guardrails.py)
```python
apply_guardrails(*, classification, facts, resolution, counters, settings,
                 limit_exceeded: str | None = None) -> GuardrailDecision
```
- `GuardrailDecision` (Pydantic): `final_outcome: Outcome`, `hits: list[GuardrailHit]`, `reasons: list[str]` (one message per hit, e.g. `"G2: restricted resource needs approval"`), `sanitized_resolution: Resolution | None`.
- Start = `resolution.proposed_outcome`, or ESCALATED when there is no resolution. Rules can only raise the outcome (asserted inside; property-tested over 13,824 combinations).
- **Use `decision.final_outcome` as the ticket outcome.** `sanitized_resolution.proposed_outcome` still holds what the model proposed. Send the SANITIZED steps and handoff note to the requester and to `add_comment` / `update_ticket` (G6 redaction), never the raw resolution.
- Rule order (affects only the order of recorded hits): G7, G1, G5, G2, G3, G4, G6. A rule is recorded only when it RAISES the outcome. Exception: G6 is always recorded when it fires (its hit may have `from == to`). So when G7 already escalated, a G4 that would also demand ESCALATED is not listed.
- G5 fires on `limit_exceeded` (the kind from `LimitExceeded.kind`) and also when `counters` exceed `max_loop_iterations`, `max_tool_calls` or `max_input_tokens_per_ticket`. The coordinator owns the token estimate (`Counters.est_input_tokens` is not updated by `diagnose`).
- G3 uses `settings.confidence_threshold` (0.70, exactly 0.70 passes) on `min(classification, resolution)` confidence; no classification means ESCALATED.
- G4 for non-access categories: AUTO needs `kb_article_id` among `facts.kb_matches`; for `access_request`: AUTO needs `facts.access is not None`. Restricted, privileged and ineligible access is G2's job only (CR-1).
- G7: no user, disabled user, or any gap starting `required:`.

## `pre_tool_check` and PRE hits
- `pre_tool_check(name, args, *, ticket, allowed)` raises `GuardrailBlocked(reason)` for: tool not allowed, unknown tool, unknown argument names, malformed `user_id` (`u-NNN`), `resource_id` (`r-NN`), `ticket_id`, bad `query` (blank, too long, control characters), bad `category`, bad `limit` (1-5, ints only), and `get_user` / `check_access` for anyone but `ticket.requester_id`. Reasons never echo values.
- `diagnose(..., blocked: list[str] | None = None)`: each refused call is appended as `"<tool>: <reason>"` (kept even when `LimitExceeded` is raised). The coordinator should turn each entry into `GuardrailHit(rule_id="PRE", message=entry, from_outcome=<outcome so far>, to_outcome=<same>)`. The refusal is also in `facts.tool_calls` (error code `FORBIDDEN`) and in `facts.gaps` as `<tool>:FORBIDDEN`.
- Open question: `get_ticket` only checks the id format (as in the blueprint), so the model may read another ticket's notes. Consider limiting it to the current ticket id on Day 8 if no eval needs it.

## Secret scan (src/safety.py)
- `scan_secrets(text) -> list[str]` and `redact_secrets(text) -> str` (`[REDACTED]`). Patterns: `password_assignment, password_is, api_key_sk, aws_key, private_key, bearer, otp_code`. Text is normalised first (NFKC, zero-width characters removed), so redacted output is the normalised text. All KB article steps are tested to be clean.

## Eval set (33 tickets)
- EV-020..033 added: access-standard x4 (EV-020..023, AUTO_RESOLVED), access-restricted x5 (EV-024..028, PENDING_APPROVAL; EV-027 is standard but the role is ineligible), security x5 (EV-029..033, ESCALATED). Dev: EV-020, 022, 024, 025, 026, 029, 030, 033 (plus the 12 from Day 6 = 20 dev). Holdout (untouched): EV-021, 023, 027, 028, 031, 032 plus the 7 from Day 6.
- `tests/test_eval_tickets.py` recomputes the access outcome labels from `data/*.json`, and checks that all security tickets trip `detect_security_terms` and that no other ticket trips either detector.
- `python evals/classify_only.py` now runs 20 dev tickets (not re-run today; the Day 6 run was 12 tickets, 100%).

## Live check (EV-024, `python scripts/smoke_diagnose.py EV-024`)
- Dev Patel (u-104) asks for the Finance Shared Drive: `get_user`, `find_resource`, `search_kb`, `check_access` -> `sensitivity=restricted`, `eligible=True`, `has_access=False`, KB-011 matched, no gaps, nothing blocked. 3 model calls, **7,274 input / 234 output tokens, $0.0169** on `claude-sonnet-5-5`. The guardrails turn a pretend AUTO_RESOLVED into PENDING_APPROVAL (G2).
- The diagnostics call is NOT prompt-cached (`cache read/write: 0/0`), unlike the classifier. About 2.3k tokens of system prompt and tool definitions are re-sent every iteration; add `cache_control` later if cost matters (Day 10 cost numbers).

## Differences from the blueprint
1. Pre-tool tests are in `tests/test_pre_tool_check.py` (blueprint: `test_guardrails.py`).
2. `apply_guardrails` also checks `counters` against the settings (defence in depth).
3. Eval labels for access tickets are checked against the reference data by a test.
4. `scripts/smoke_diagnose.py` takes an eval ticket id and prints the guardrail verdict on the real facts; holdout tickets are refused.

## Start Day 8 with
`git checkout main`, `git pull`, `git checkout -b day-08-coordinator`. Day 8: resolver (forced tool `submit_resolution`), `src/coordinator.py` (`triage()` never raises), commit step through `update_ticket` / `add_comment`, `scripts/smoke_pipeline.py`. Reuse `forced_tool_response` from `tests/fakes.py`. Never run the holdout split before Day 13.
