"""Runtime settings (src/config.py).

Everything configurable comes from environment variables (see .env.example).
Logic elsewhere must read values from Settings and never hard-code model ids,
thresholds or limits.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when an environment variable has an invalid value."""


def _str(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key)
    return default if value is None or value.strip() == "" else value.strip()


def _int(env: Mapping[str, str], key: str, default: int, *, minimum: int = 1) -> int:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}, got {value}")
    return value


def _float(env: Mapping[str, str], key: str, default: float, *, low: float, high: float) -> float:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc
    if not low <= value <= high:
        raise ConfigError(f"{key} must be between {low} and {high}, got {value}")
    return value


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    text = raw.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be true or false, got {raw!r}")


@dataclass(frozen=True)
class Settings:
    # API access (never logged: repr=False)
    anthropic_api_key: str | None = field(default=None, repr=False)

    # Models, one per role
    model_classifier: str = "claude-haiku-5-5"
    model_summarizer: str = "claude-haiku-5-5"
    model_diagnostics: str = "claude-sonnet-5-5"
    model_resolver: str = "claude-sonnet-5-5"

    # Guardrails and budgets
    confidence_threshold: float = 0.70
    max_loop_iterations: int = 8
    max_tool_calls: int = 10
    max_input_tokens_per_ticket: int = 20000
    thread_summary_trigger_messages: int = 6
    thread_summary_trigger_tokens: int = 3000

    # Audit
    audit_log_path: str = "logs/audit.jsonl"

    # Web demo
    rate_limit_per_minute: int = 5
    daily_call_cap: int = 150
    max_concurrent_triages: int = 2
    request_timeout_seconds: float = 60.0
    trusted_proxy: bool = False

    # Tests only: JSON like {"get_user": "TIMEOUT_ONCE"} read by the MCP servers
    fault_inject: str | None = None

    @property
    def models(self) -> dict[str, str]:
        return {
            "classifier": self.model_classifier,
            "diagnostics": self.model_diagnostics,
            "resolver": self.model_resolver,
            "summarizer": self.model_summarizer,
        }

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e: Mapping[str, str] = os.environ if env is None else env
        d = cls()
        key = e.get("ANTHROPIC_API_KEY")
        return cls(
            anthropic_api_key=key.strip() if key and key.strip() else None,
            model_classifier=_str(e, "MODEL_CLASSIFIER", d.model_classifier),
            model_summarizer=_str(e, "MODEL_SUMMARIZER", d.model_summarizer),
            model_diagnostics=_str(e, "MODEL_DIAGNOSTICS", d.model_diagnostics),
            model_resolver=_str(e, "MODEL_RESOLVER", d.model_resolver),
            confidence_threshold=_float(
                e, "CONFIDENCE_THRESHOLD", d.confidence_threshold, low=0.0, high=1.0
            ),
            max_loop_iterations=_int(e, "MAX_LOOP_ITERATIONS", d.max_loop_iterations),
            max_tool_calls=_int(e, "MAX_TOOL_CALLS", d.max_tool_calls),
            max_input_tokens_per_ticket=_int(
                e, "MAX_INPUT_TOKENS_PER_TICKET", d.max_input_tokens_per_ticket, minimum=1000
            ),
            thread_summary_trigger_messages=_int(
                e, "THREAD_SUMMARY_TRIGGER_MESSAGES", d.thread_summary_trigger_messages
            ),
            thread_summary_trigger_tokens=_int(
                e, "THREAD_SUMMARY_TRIGGER_TOKENS", d.thread_summary_trigger_tokens, minimum=100
            ),
            audit_log_path=_str(e, "AUDIT_LOG_PATH", d.audit_log_path),
            rate_limit_per_minute=_int(e, "RATE_LIMIT_PER_MINUTE", d.rate_limit_per_minute),
            daily_call_cap=_int(e, "DAILY_CALL_CAP", d.daily_call_cap),
            max_concurrent_triages=_int(e, "MAX_CONCURRENT_TRIAGES", d.max_concurrent_triages),
            request_timeout_seconds=_float(
                e, "REQUEST_TIMEOUT_SECONDS", d.request_timeout_seconds, low=1.0, high=600.0
            ),
            trusted_proxy=_bool(e, "TRUSTED_PROXY", d.trusted_proxy),
            fault_inject=(e.get("FAULT_INJECT") or None),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load .env once (if present) and return the process-wide settings."""
    load_dotenv()
    return Settings.from_env()
