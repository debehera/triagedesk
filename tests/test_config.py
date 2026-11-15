"""Tests for src/config.py (NFR-5: configuration only through environment variables)."""

import pytest

from src.config import ConfigError, Settings


def test_defaults_with_empty_environment():
    s = Settings.from_env({})
    assert s.anthropic_api_key is None
    assert s.confidence_threshold == 0.70
    assert (s.max_loop_iterations, s.max_tool_calls) == (8, 10)
    assert s.daily_call_cap == 150
    assert s.trusted_proxy is False


def test_models_property_covers_all_roles():
    assert set(Settings.from_env({}).models) == {
        "classifier",
        "diagnostics",
        "resolver",
        "summarizer",
    }


def test_overrides_are_parsed():
    s = Settings.from_env(
        {
            "MODEL_CLASSIFIER": "my-model",
            "CONFIDENCE_THRESHOLD": "0.8",
            "MAX_TOOL_CALLS": "3",
            "TRUSTED_PROXY": "TRUE",
            "ANTHROPIC_API_KEY": " sk-test ",
        }
    )
    assert s.models["classifier"] == "my-model"
    assert s.confidence_threshold == 0.8
    assert s.max_tool_calls == 3
    assert s.trusted_proxy is True
    assert s.anthropic_api_key == "sk-test"


@pytest.mark.parametrize(
    "env",
    [
        {"MAX_TOOL_CALLS": "many"},
        {"MAX_TOOL_CALLS": "0"},
        {"CONFIDENCE_THRESHOLD": "1.5"},
        {"CONFIDENCE_THRESHOLD": "high"},
        {"TRUSTED_PROXY": "maybe"},
        {"REQUEST_TIMEOUT_SECONDS": "0"},
    ],
)
def test_invalid_values_fail_fast(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_api_key_is_never_in_repr():
    assert "sk-secret" not in repr(Settings.from_env({"ANTHROPIC_API_KEY": "sk-secret"}))
