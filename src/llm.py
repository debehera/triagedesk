"""The only module that talks to the Anthropic SDK (docs/ARCHITECTURE.md, ADR-016).

Everything else depends on the small `LLMClient` protocol, so tests can swap in a fake that
returns scripted responses. This file owns: model choice per role, retries with back-off,
usage and cost, and the translation of SDK objects into plain dicts and dataclasses.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from src.config import Settings
from src.cost import compute_cost
from src.schemas import Usage

# ---------- errors raised to the rest of the app ----------


class LLMError(Exception):
    """Base class for every failure of a model call."""


class LLMUnavailable(LLMError):
    """Transient problem (rate limit, network, server error) that survived all retries."""


class LLMBudgetExhausted(LLMError):
    """The workspace or monthly spend limit is used up. Never retried (API.md C-4)."""


class LLMRequestError(LLMError):
    """The request itself was rejected (bad key, invalid request). Retrying cannot help."""


# ---------- response types (blueprint B4) ----------


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens" | "refusal" | other
    text: str  # concatenated text blocks
    tool_uses: list[ToolUse] = field(default_factory=list)
    content: list[dict[str, Any]] = field(default_factory=list)  # appended to history as-is
    usage: Usage = field(default_factory=Usage)


class LLMClient(Protocol):
    async def create(
        self,
        *,
        role: str,  # "classifier" | "diagnostics" | "resolver" | "summarizer"
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...


# ---------- helpers ----------

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 1.0

_RETRYABLE = (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError)


def _is_budget_error(exc: anthropic.APIStatusError) -> bool:
    """The documented spend-limit rejection: HTTP 400 mentioning the API usage limits."""
    return exc.status_code == 400 and "usage limit" in str(getattr(exc, "message", exc)).lower()


def _to_usage(raw: Any, model: str) -> Usage:
    usage = Usage(
        input_tokens=getattr(raw, "input_tokens", 0) or 0,
        output_tokens=getattr(raw, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
    )
    usage.cost_usd = compute_cost(model, usage)
    return usage


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Keep only the fields the API accepts back, so history never carries extra fields."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return block.model_dump(exclude_none=True)


def convert_response(resp: Any, model: str) -> LLMResponse:
    """Turn an SDK Message into an LLMResponse (pure function, unit-tested)."""
    content = [_block_to_dict(b) for b in resp.content]
    text = "".join(b["text"] for b in content if b["type"] == "text")
    tool_uses = [
        ToolUse(id=b["id"], name=b["name"], input=dict(b["input"]))
        for b in content
        if b["type"] == "tool_use"
    ]
    return LLMResponse(
        stop_reason=str(resp.stop_reason or "unknown"),
        text=text,
        tool_uses=tool_uses,
        content=content,
        usage=_to_usage(resp.usage, model),
    )


# ---------- the real client ----------


class AnthropicLLM:
    """LLMClient backed by the Anthropic Messages API."""

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        if client is None:
            if not settings.anthropic_api_key:
                raise LLMRequestError("ANTHROPIC_API_KEY is not set (see .env.example)")
            # max_retries=0: this class owns the retry policy, so retries are not multiplied.
            client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.request_timeout_seconds,
                max_retries=0,
            )
        self._client = client

    async def create(
        self,
        *,
        role: str,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        try:
            model = self._settings.models[role]
        except KeyError as exc:
            raise ValueError(f"unknown role {role!r}") from exc

        params: dict[str, Any] = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = tools
        if tool_choice:
            params["tool_choice"] = tool_choice

        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = await self._client.messages.create(**params)
                return convert_response(resp, model)
            except _RETRYABLE as exc:
                last_error = exc
            except anthropic.APIStatusError as exc:
                if _is_budget_error(exc):
                    raise LLMBudgetExhausted("API spend limit reached") from exc
                if exc.status_code == 529 or exc.status_code >= 500:
                    last_error = exc  # "overloaded" and other server-side failures
                else:
                    # 400/401/403/404 ...: our request is wrong; never echo secrets
                    raise LLMRequestError(f"request rejected (HTTP {exc.status_code})") from exc
            if attempt < MAX_ATTEMPTS - 1:
                delay = BASE_DELAY_SECONDS * (2**attempt) + random.uniform(0, 0.25)
                await self._sleep(delay)
        raise LLMUnavailable(f"model call failed after {MAX_ATTEMPTS} attempts") from last_error
