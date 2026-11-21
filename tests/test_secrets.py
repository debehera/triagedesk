"""Secret scanning (guardrail G6): one positive per pattern, KB text must stay clean."""

import pytest

from src.data import load_kb
from src.safety import REDACTED, SECRET_PATTERNS, redact_secrets, scan_secrets

POSITIVES = {
    "password_assignment": "Use password: Winter2026! to sign in.",
    "password_is": "Your new password is Tr0ub4dor&3 for now.",
    "api_key_sk": "The key is sk-ant-abcdefghijklmnopqrstuvwxyz0123456789.",
    "aws_key": "Access key AKIAIOSFODNN7EXAMPLE was used.",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIB...",
    "bearer": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
    "otp_code": "Your verification code is 482913, enter it now.",
}

BENIGN = [
    "Click Forgot password on the sign-in page.",
    "Enter your new password twice and select Save.",
    "Choose a password that is at least 12 characters long.",
    "If the account is locked, wait 15 minutes or contact the service desk.",
    "Open Software Center and select Install.",
    "Approve the sign-in request in the authenticator app.",
    "The verification email arrives within a few minutes.",
    "Restart the VPN client and sign in again.",
]


def test_every_pattern_has_a_positive_example():
    assert set(POSITIVES) == set(SECRET_PATTERNS)


@pytest.mark.parametrize(("name", "text"), POSITIVES.items())
def test_pattern_fires(name, text):
    assert name in scan_secrets(text)


@pytest.mark.parametrize("text", BENIGN)
def test_benign_wording_is_clean(text):
    assert scan_secrets(text) == []


def test_no_kb_article_trips_the_scanner():
    for article in load_kb():
        for step in [article.title, *article.steps]:
            assert scan_secrets(step) == [], (article.id, step)


@pytest.mark.parametrize(("name", "text"), POSITIVES.items())
def test_redaction_removes_the_secret(name, text):
    redacted = redact_secrets(text)
    assert REDACTED in redacted
    assert scan_secrets(redacted) == []


def test_redaction_keeps_the_harmless_text():
    out = redact_secrets("Sign in with password: Winter2026! then restart Outlook.")
    assert out == f"Sign in with {REDACTED} then restart Outlook."
    assert "Winter2026" not in out


def test_clean_text_is_unchanged():
    assert redact_secrets("Restart the VPN client.") == "Restart the VPN client."


def test_zero_width_characters_cannot_hide_a_secret():
    assert "password_assignment" in scan_secrets("pass​word: hunter22")
    assert "hunter22" not in redact_secrets("pass​word: hunter22")
