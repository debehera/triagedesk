# Handoff: Day 6 -> Day 7

## State at the end of Day 6
- Branch `day-06-classifier` (merge to `main` after the checks).
- New: `src/schema_utils.py`, `src/safety.py`, `src/prompts/classifier.py`, `src/agents/classifier.py`, `src/cli.py`, `examples/tickets/{phishing,vague}.json`, `evals/tickets.jsonl` (EV-001..019), `evals/labels-notes.md`, `evals/classify_only.py`, `tests/test_schema_utils.py`, `tests/test_safety.py`, `tests/test_classifier.py`, `tests/test_cli.py`, `tests/test_eval_tickets.py`.
- Modified: `tests/fakes.py` (adds `forced_tool_response`).
- 364 tests pass offline; `ruff check .` clean.

## Classifier (`src/agents/classifier.py`)
- `await classify(llm, ticket, thread_summary, settings) -> (Classification, Usage, attempts)`. Forced tool call `submit_classification` (schema from `tool_schema(Classification)`), `max_tokens=512`, up to 3 attempts; the Pydantic error (field names and rules, never the bad values) goes back as an `is_error` tool_result. `ClassificationError(last_error, usage=, attempts=)` after 3 failures; the coordinator must catch it, and it carries the cost already spent. LLM errors (`LLMUnavailable`, `LLMBudgetExhausted`) propagate.
- After the model answers, CODE adds `injection_suspected` (`detect_injection`) and `security_terms` (`detect_security_terms`) to `risk_flags` (no duplicates, never removes a flag). Text checked = subject + body + every REQUESTER message in `ticket.thread` (agent and IT messages are ignored).
- The system prompt is one fixed text (rubric + 6 new few-shot examples) with `cache_control: ephemeral`. Measured on `claude-haiku-5-5`: about 2,350 prompt tokens; first call `cache write 2350`, later calls `cache read 2350`. Cost per classification about $0.0001-0.0004.
- No `temperature` is sent (not verified for these models; the API worked without it).

## Detectors (`src/safety.py`)
- `detect_injection`, `detect_security_terms` plus `injection_matches` / `security_matches` (names of the patterns that fired, for traces and tests). Text is NFKC-normalised and zero-width characters are removed first.
- Injection patterns: `ignore_previous, disregard_instructions, system_prompt, you_are_now, system_prefix, act_as_admin, reveal_prompt, override_rules, jailbreak, force_outcome, auto_approve`.
- Security patterns: `phishing, malware, compromise, theft, lost_device, unauthorised, suspicious, credentials_entered (both word orders), data_leak, someone_logged_in, unfamiliar_signin`. The last one and the reversed `credentials_entered` are additions beyond the blueprint (for EV-031 and EV-029).
- Both are flags only. Day 7's G1 must treat `RiskFlag.SECURITY_TERMS` like a security category.

## Testing without the API
- Script a classifier reply with `forced_tool_response("submit_classification", {...})` from `tests/fakes.py` (one reply per attempt; an invalid dict triggers the retry path). Reuse it for the resolver on Day 8 (`submit_resolution`).

## Live results (dev split, 12 tickets, `claude-haiku-5-5`)
- Category accuracy 100%, severity within +-1 100%, no retries, no errors. Low confidence (<0.7) on exactly the five ambiguous/multi-issue tickets EV-013, 014, 016 (access_request, accepted), 017, 018.
- Phishing sample: `security_incident` P2, 0.9, flags `security_keywords` + `security_terms`. Vague sample: `other`, 0.2, `ambiguous`.
- Watch on Day 7/8/10: EV-001 (clear VPN) came back P2, confidence 0.75, flag `ambiguous`; EV-009 came back P2. Confidence 0.75 is near the 0.70 threshold of G3.
- The holdout split (EV-002, 004, 006, 008, 010, 015, 019) has NOT been run or looked at. `classify_only.py` refuses it without `--include-holdout`; do not use that before Day 13.

## Differences from the blueprint
1. `classify_only.py` runs the 12 dev tickets by default (holdout refused), has `--max-cost` (default $0.50) and `--ids`.
2. Detector patterns: two additions (above); thread text of the requester is also scanned.
3. `tests/test_eval_tickets.py` (basic eval-set checks) arrives on Day 6; Day 10 extends it to 43 tickets.
4. Few-shot example 3 is a missing badge plus a monitor fault (not the blueprint's forgotten password).

## Start Day 7 with
`git checkout main`, `git pull`, `git checkout -b day-07-guardrails`. Day 7: guardrails G1-G7, the full `pre_tool_check`, `scan_secrets`, and 14 more eval tickets (EV-020..033). No API calls are needed except the final live check.
