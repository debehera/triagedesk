"""Shared helpers for both MCP servers (directory now, itsm on Day 4).

Rules every tool follows (CLAUDE.md rule 4, docs/API.md section 7):
  * success -> {"ok": True, "data": {...}}
  * failure -> {"ok": False, "error": {"code", "message", "retryable"}}
  * a tool never raises to the caller and never prints to stdout (stdout carries the protocol).
"""

from __future__ import annotations

import functools
import json
import os
import re
import sys
from collections.abc import Callable
from typing import Any

# [0-9] instead of \d so that look-alike digits from other scripts are rejected.
USER_ID_RE = re.compile(r"u-[0-9]{3}")
RESOURCE_ID_RE = re.compile(r"r-[0-9]{2}")


def ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def err(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "retryable": retryable}}


def log(message: str) -> None:
    """Diagnostics go to stderr, never stdout."""
    print(message, file=sys.stderr)


def valid_user_id(value: object) -> bool:
    return isinstance(value, str) and USER_ID_RE.fullmatch(value) is not None


def valid_resource_id(value: object) -> bool:
    return isinstance(value, str) and RESOURCE_ID_RE.fullmatch(value) is not None


# ---------- fault injection (tests and demos only) ----------

_once_seen: set[str] = set()


def reset_faults() -> None:
    """Forget which TIMEOUT_ONCE faults already fired (call from a test fixture)."""
    _once_seen.clear()


def maybe_fault(tool_name: str) -> dict[str, Any] | None:
    """Return an error envelope if FAULT_INJECT asks this tool to fail, else None.

    FAULT_INJECT is JSON such as {"get_user": "TIMEOUT_ONCE"}. It is read on every call
    (not at import time) so tests can change it with monkeypatch.setenv.
    Kinds: TIMEOUT and INTERNAL (retryable), NOT_FOUND (not retryable), TIMEOUT_ONCE
    (a retryable timeout on the first call only).
    """
    raw = os.environ.get("FAULT_INJECT", "").strip()
    if not raw:
        return None
    try:
        config = json.loads(raw)
        kind = config.get(tool_name) if isinstance(config, dict) else None
    except ValueError:
        log("FAULT_INJECT is not valid JSON; ignoring it")
        return None
    if kind == "TIMEOUT_ONCE":
        if tool_name in _once_seen:
            return None
        _once_seen.add(tool_name)
        return err("TIMEOUT", f"{tool_name} timed out (injected fault)", retryable=True)
    if kind == "TIMEOUT":
        return err("TIMEOUT", f"{tool_name} timed out (injected fault)", retryable=True)
    if kind == "INTERNAL":
        return err("INTERNAL", f"{tool_name} failed internally (injected fault)", retryable=True)
    if kind == "NOT_FOUND":
        return err("NOT_FOUND", f"{tool_name} found nothing (injected fault)")
    if kind is not None:
        log(f"Unknown FAULT_INJECT kind {kind!r} for {tool_name}; ignoring it")
    return None


def tool_guard(tool_name: str) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """Decorator for tool functions: apply fault injection first, then turn any unexpected
    exception into an INTERNAL envelope so the caller never sees a traceback.

    functools.wraps copies the name, docstring and type hints, which FastMCP reads to build
    the tool description and argument schema the model sees.
    """

    def decorator(fn: Callable[..., dict]) -> Callable[..., dict]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict:
            if (fault := maybe_fault(tool_name)) is not None:
                return fault
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - deliberate catch-all at the tool boundary
                log(f"{tool_name} crashed: {type(exc).__name__}: {exc}")
                return err("INTERNAL", f"{tool_name} failed unexpectedly", retryable=True)

        return wrapper

    return decorator
