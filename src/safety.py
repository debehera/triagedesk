"""Deterministic text detectors (blueprint Day 6, steps 6 and 6b; ADR-020 / CR-2).

Both functions only RAISE FLAGS. They never decide an outcome: a false positive costs one extra
escalation, a false negative is the real risk, so the patterns lean towards matching. Each
pattern has a name so tests (and the trace) can say exactly which one fired. Every pattern list
is the single place to edit; record changes in `evals/labels-notes.md`.
"""

from __future__ import annotations

import re
import unicodedata

_FLAGS = re.IGNORECASE | re.MULTILINE | re.DOTALL


def _compile(patterns: dict[str, str]) -> dict[str, re.Pattern[str]]:
    return {name: re.compile(rx, _FLAGS) for name, rx in patterns.items()}


INJECTION_PATTERNS = _compile(
    {
        "ignore_previous": r"\bignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above)\s+"
        r"(?:instructions|rules)",
        "disregard_instructions": r"\bdisregard\b.{0,60}\b(?:instructions|rules)\b",
        "system_prompt": r"\bsystem\s+prompt\b",
        "you_are_now": r"\byou\s+are\s+now\b",
        "system_prefix": r"^\s*system\s*:",
        "act_as_admin": r"\bact\s+as\s+(?:the\s+)?(?:admin|administrator|ciso)\b",
        "reveal_prompt": r"\breveal\b.{0,60}\b(?:prompt|instructions)\b",
        "override_rules": r"\boverrid(?:e|es|ing)\b.{0,40}\b(?:rules?|polic\w+|guardrails?|"
        r"instructions?)\b",
        "jailbreak": r"\bjailbreak",
        "force_outcome": r"\bforce\b.{0,30}\boutcome",
        "auto_approve": r"\bauto[-\s]?approv\w*",
    }
)

SECURITY_PATTERNS = _compile(
    {
        "phishing": r"\bphish\w*",
        "malware": r"\b(?:ransom\w*|malware|spyware|keylogger|trojan|botnet|virus(?:es)?)\b",
        "compromise": r"\b(?:compromis\w*|hack\w*|breach\w*)",
        "theft": r"\b(?:stolen|theft|stole|thief|steal\w*)\b",
        "lost_device": r"\b(?:lost|missing)\b\W+(?:\w+\W+){0,4}?"
        r"(?:laptop|phone|device|badge|token|usb|yubikey)\b"
        r"|\b(?:laptop|phone|device|badge|token|usb|yubikey)\b\W+(?:\w+\W+){0,3}?"
        r"(?:lost|missing)\b",
        "unauthorised": r"\bunauthori[sz]ed\b",
        "suspicious": r"\bsuspicious\s+(?:login|sign-?in|activity|email|link|attachment|message)",
        "credentials_entered": r"\b(?:entered|typed|gave|shared)\b.{0,40}"
        r"\b(?:credentials|password)\b.{0,60}\b(?:link|site|page|email|website)\b"
        r"|\b(?:link|site|page|email|website)\b.{0,80}\b(?:entered|typed|gave|shared)\b"
        r".{0,40}\b(?:credentials|password)\b",
        "data_leak": r"\bdata\s+(?:leak|breach|exposure)|\bleaked\b|\bexfiltrat\w*",
        "someone_logged_in": r"\bsomeone(?:\s+else)?\s+(?:logged|signed)\s+in\b",
        "unfamiliar_signin": r"\b(?:login|log-?in|sign-?in)\s+(?:alert|attempt|notification)s?\b"
        r".{0,80}\b(?:unfamiliar|unknown|unrecogni[sz]ed|foreign|another country|"
        r"different country)\b"
        r"|\b(?:unfamiliar|unknown|unrecogni[sz]ed)\s+(?:login|log-?in|sign-?in|device|location)",
    }
)

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))


def _normalise(text: str) -> str:
    """Fold look-alike characters and drop zero-width ones so they cannot hide a keyword."""
    return unicodedata.normalize("NFKC", text).translate(_INVISIBLE)


def injection_matches(text: str) -> list[str]:
    """Names of the injection patterns found in `text` (empty list: none)."""
    clean = _normalise(text)
    return [name for name, rx in INJECTION_PATTERNS.items() if rx.search(clean)]


def security_matches(text: str) -> list[str]:
    """Names of the security-term patterns found in `text` (empty list: none)."""
    clean = _normalise(text)
    return [name for name, rx in SECURITY_PATTERNS.items() if rx.search(clean)]


def detect_injection(text: str) -> bool:
    """True when the text looks like it tries to give instructions to the AI. A flag only."""
    return bool(injection_matches(text))


def detect_security_terms(text: str) -> bool:
    """True when the text uses security-incident wording (CR-2, drives guardrail G1)."""
    return bool(security_matches(text))


# ---------- secret scanning (blueprint Day 7, step 3; guardrail G6) ----------

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(rx)
    for name, rx in {
        "password_assignment": r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+",
        "password_is": r"(?i)(your|the|new|temporary|temp)\s+password\s+is\s+\S+",
        "api_key_sk": r"\bsk-[A-Za-z0-9_-]{20,}",
        "aws_key": r"\bAKIA[0-9A-Z]{16}\b",
        "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "bearer": r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}",
        "otp_code": r"(?i)\b(otp|mfa|2fa|verification)\s*(code)?\s*(is|:)\s*\d{4,8}\b",
    }.items()
}

REDACTED = "[REDACTED]"


def scan_secrets(text: str) -> list[str]:
    """Names of the secret-like patterns found in `text` (empty list: clean)."""
    clean = _normalise(text)
    return [name for name, rx in SECRET_PATTERNS.items() if rx.search(clean)]


def redact_secrets(text: str) -> str:
    """Replace every secret-like match with [REDACTED] (works on the normalised text)."""
    clean = _normalise(text)
    for rx in SECRET_PATTERNS.values():
        clean = rx.sub(REDACTED, clean)
    return clean
