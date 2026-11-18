"""Classifier agent (blueprint Day 6, B7): a forced tool call returning a validated Classification.

The model is forced to call `submit_classification`, whose input schema is the `Classification`
model, so the answer is schema-shaped. If validation still fails, the error is fed back to the
model (at most two retries). After the model, CODE adds two risk flags from deterministic
detectors, so a model that misses an injection or a security term cannot lower the risk.
"""

from __future__ import annotations

from pydantic import ValidationError

from src.config import Settings
from src.llm import LLMClient, LLMResponse
from src.prompts.classifier import CLASSIFIER_SYSTEM
from src.prompts.render import render_ticket
from src.safety import detect_injection, detect_security_terms
from src.schema_utils import tool_schema
from src.schemas import Classification, RiskFlag, Ticket, Usage

TOOL_NAME = "submit_classification"
MAX_ATTEMPTS = 3  # 1 try + 2 retries
MAX_TOKENS = 512


class ClassificationError(Exception):
    """The model never produced a valid classification. Carries what was spent."""

    def __init__(self, last_error: str, *, usage: Usage, attempts: int) -> None:
        super().__init__(f"classification failed after {attempts} attempts: {last_error}")
        self.last_error = last_error
        self.usage = usage
        self.attempts = attempts


def _short_error(exc: ValidationError) -> str:
    """Field names and rules only (no echo of the model's own values), at most 300 characters."""
    parts = [f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in exc.errors()]
    return "; ".join(parts)[:300]


def _text_to_check(ticket: Ticket) -> str:
    """Everything the requester wrote: subject, body and every requester message in the thread."""
    pieces = [ticket.subject, ticket.body]
    pieces += [m.text for m in ticket.thread if m.role == "requester"]
    return "\n".join(pieces)


async def classify(
    llm: LLMClient, ticket: Ticket, thread_summary: str | None, settings: Settings
) -> tuple[Classification, Usage, int]:
    """Return (classification, total usage, attempts). Raises ClassificationError."""
    system = [{"type": "text", "text": CLASSIFIER_SYSTEM, "cache_control": {"type": "ephemeral"}}]
    tools = [
        {
            "name": TOOL_NAME,
            "description": "Submit the classification of this ticket.",
            "input_schema": tool_schema(Classification),
        }
    ]
    messages: list[dict] = [{"role": "user", "content": render_ticket(ticket, thread_summary)}]
    usage = Usage()
    last_error = "no attempt made"
    classification: Classification | None = None
    attempt = 0

    while attempt < MAX_ATTEMPTS:
        attempt += 1
        resp: LLMResponse = await llm.create(
            role="classifier",
            system=system,
            messages=messages,
            tools=tools,
            tool_choice={"type": "tool", "name": TOOL_NAME},
            max_tokens=MAX_TOKENS,
        )
        usage = usage + resp.usage
        tool_use = next((t for t in resp.tool_uses if t.name == TOOL_NAME), None)

        if tool_use is None:
            last_error = f"the model did not call {TOOL_NAME} (stop_reason={resp.stop_reason})"
            if resp.content:  # an assistant message may not be empty
                messages += [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content": f"Call {TOOL_NAME} exactly once."},
                ]
            continue

        try:
            classification = Classification.model_validate(tool_use.input)
            break
        except ValidationError as exc:
            last_error = _short_error(exc)
            messages += [
                {"role": "assistant", "content": resp.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": f"Invalid: {last_error}. Call {TOOL_NAME} again.",
                            "is_error": True,
                        }
                    ],
                },
            ]

    if classification is None:
        raise ClassificationError(last_error, usage=usage, attempts=attempt)

    flags = list(classification.risk_flags)
    text = _text_to_check(ticket)
    if detect_injection(text):
        flags.append(RiskFlag.INJECTION_SUSPECTED)
    if detect_security_terms(text):
        flags.append(RiskFlag.SECURITY_TERMS)
    classification = classification.model_copy(update={"risk_flags": list(dict.fromkeys(flags))})
    return classification, usage, attempt
