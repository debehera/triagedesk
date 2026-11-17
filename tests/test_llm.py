"""Tests for src/cost.py and src/llm.py. No network: the SDK client is replaced by a stub."""

from types import SimpleNamespace

import anthropic
import httpx
import pytest

from src.config import Settings
from src.cost import compute_cost
from src.llm import (
    AnthropicLLM,
    LLMBudgetExhausted,
    LLMRequestError,
    LLMUnavailable,
    convert_response,
)
from src.schemas import Usage

PRICING = {
    "m": {
        "input_per_mtok": 1.0,
        "output_per_mtok": 5.0,
        "cache_read_per_mtok": 0.1,
        "cache_write_per_mtok": 1.25,
    }
}


# ---------- cost ----------


def test_cost_math_with_all_four_token_kinds():
    usage = Usage(
        input_tokens=1_000_000,
        output_tokens=200_000,
        cache_read_tokens=500_000,
        cache_write_tokens=80_000,
    )
    assert compute_cost("m", usage, PRICING) == pytest.approx(1.0 + 1.0 + 0.05 + 0.1)


def test_unknown_model_costs_zero_and_warns_once(capsys):
    usage = Usage(input_tokens=10, output_tokens=10)
    assert compute_cost("typo-model", usage, PRICING) == 0.0
    assert compute_cost("typo-model", usage, PRICING) == 0.0
    assert capsys.readouterr().err.count("typo-model") == 1


def test_real_pricing_file_prices_the_default_models():
    for model in Settings.from_env({}).models.values():
        assert compute_cost(model, Usage(input_tokens=1000, output_tokens=1000)) > 0


# ---------- response conversion ----------


def sdk_response(blocks, stop_reason="end_turn", usage=None):
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=usage or SimpleNamespace(input_tokens=100, output_tokens=20),
    )


TEXT = SimpleNamespace(type="text", text="DONE")
TOOL = SimpleNamespace(type="tool_use", id="toolu_1", name="get_user", input={"user_id": "u-101"})


def test_text_and_tool_blocks_are_converted_to_plain_dicts():
    resp = convert_response(sdk_response([TEXT, TOOL], "tool_use"), "m")
    assert resp.stop_reason == "tool_use" and resp.text == "DONE"
    assert resp.content == [
        {"type": "text", "text": "DONE"},
        {"type": "tool_use", "id": "toolu_1", "name": "get_user", "input": {"user_id": "u-101"}},
    ]
    assert [(t.id, t.name, t.input) for t in resp.tool_uses] == [
        ("toolu_1", "get_user", {"user_id": "u-101"})
    ]


def test_missing_cache_fields_count_as_zero():
    usage = convert_response(sdk_response([TEXT]), "m").usage
    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (0, 0)
    assert (usage.input_tokens, usage.output_tokens) == (100, 20)


def test_cache_fields_none_count_as_zero_and_present_values_are_kept():
    raw = SimpleNamespace(
        input_tokens=5, output_tokens=6, cache_read_input_tokens=None, cache_creation_input_tokens=7
    )
    usage = convert_response(sdk_response([TEXT], usage=raw), "m").usage
    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (0, 7)


def test_unknown_stop_reason_becomes_the_word_unknown():
    assert convert_response(sdk_response([TEXT], stop_reason=None), "m").stop_reason == "unknown"


# ---------- the client: retries and error mapping ----------


class StubMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_llm(script):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    stub = SimpleNamespace(messages=StubMessages(script))
    llm = AnthropicLLM(Settings.from_env({}), client=stub, sleep=fake_sleep)
    return llm, stub.messages, sleeps


def status_error(cls, status, message="boom"):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(message, response=httpx.Response(status, request=request), body=None)


async def call(llm, **extra):
    return await llm.create(
        role="classifier", system=[{"type": "text", "text": "s"}], messages=[], **extra
    )


async def test_success_uses_the_model_for_the_role_and_omits_unused_parameters():
    llm, messages, _ = make_llm([sdk_response([TEXT])])
    resp = await call(llm)
    sent = messages.calls[0]
    assert sent["model"] == "claude-haiku-5-5" and "tools" not in sent and "tool_choice" not in sent
    assert resp.text == "DONE" and resp.usage.cost_usd > 0


async def test_tools_and_forced_tool_choice_are_passed_through():
    llm, messages, _ = make_llm([sdk_response([TEXT])])
    tools = [{"name": "t", "description": "d", "input_schema": {"type": "object"}}]
    await call(llm, tools=tools, tool_choice={"type": "tool", "name": "t"})
    assert messages.calls[0]["tools"] == tools
    assert messages.calls[0]["tool_choice"] == {"type": "tool", "name": "t"}


async def test_diagnostics_role_uses_the_diagnostics_model():
    llm, messages, _ = make_llm([sdk_response([TEXT])])
    await llm.create(role="diagnostics", system=[], messages=[])
    assert messages.calls[0]["model"] == "claude-sonnet-5-5"


async def test_unknown_role_is_a_programming_error():
    llm, _, _ = make_llm([])
    with pytest.raises(ValueError):
        await llm.create(role="poet", system=[], messages=[])


async def test_retries_twice_then_succeeds_with_backoff():
    errors = [
        status_error(anthropic.RateLimitError, 429),
        status_error(anthropic.InternalServerError, 500),
    ]
    llm, messages, sleeps = make_llm([*errors, sdk_response([TEXT])])
    assert (await call(llm)).text == "DONE"
    assert len(messages.calls) == 3
    assert 1.0 <= sleeps[0] < 1.5 and 2.0 <= sleeps[1] < 2.5


async def test_gives_up_after_three_attempts():
    errors = [status_error(anthropic.InternalServerError, 500) for _ in range(3)]
    llm, messages, sleeps = make_llm(errors)
    with pytest.raises(LLMUnavailable):
        await call(llm)
    assert len(messages.calls) == 3 and len(sleeps) == 2


async def test_connection_errors_and_overloaded_529_are_retried():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    script = [
        anthropic.APIConnectionError(request=request),
        status_error(anthropic.APIStatusError, 529, "overloaded"),
        sdk_response([TEXT]),
    ]
    llm, messages, _ = make_llm(script)
    assert (await call(llm)).text == "DONE" and len(messages.calls) == 3


async def test_spend_limit_is_not_retried():
    message = (
        "You have reached your specified API usage limits. You will regain access on 2026-12-01."
    )
    llm, messages, sleeps = make_llm([status_error(anthropic.BadRequestError, 400, message)])
    with pytest.raises(LLMBudgetExhausted):
        await call(llm)
    assert len(messages.calls) == 1 and sleeps == []


async def test_other_bad_requests_are_not_retried_and_do_not_leak_details():
    llm, messages, _ = make_llm([status_error(anthropic.BadRequestError, 400, "secret detail")])
    with pytest.raises(LLMRequestError) as info:
        await call(llm)
    assert "secret" not in str(info.value) and len(messages.calls) == 1


async def test_authentication_errors_fail_fast():
    llm, messages, _ = make_llm([status_error(anthropic.AuthenticationError, 401, "bad key")])
    with pytest.raises(LLMRequestError):
        await call(llm)
    assert len(messages.calls) == 1


def test_missing_api_key_fails_fast_with_a_clear_message():
    with pytest.raises(LLMRequestError, match="ANTHROPIC_API_KEY"):
        AnthropicLLM(Settings.from_env({}))


def test_real_client_is_built_without_sdk_retries():
    llm = AnthropicLLM(Settings.from_env({"ANTHROPIC_API_KEY": "sk-test"}))
    assert llm._client.max_retries == 0
