"""CLI `classify` with a fake model."""

import json
from pathlib import Path

from src.cli import main, run_classify
from src.config import Settings
from tests.fakes import FakeLLM, forced_tool_response

SETTINGS = Settings.from_env({})
ROOT = Path(__file__).resolve().parent.parent
GOOD = {
    "category": "security_incident",
    "severity": "P2",
    "confidence": 0.9,
    "affected_system": "mailbox",
    "summary": "Credentials entered on a suspicious page.",
    "risk_flags": [],
}


async def test_prints_classification_attempts_and_cost(capsys):
    llm = FakeLLM([forced_tool_response("submit_classification", GOOD)])
    code = await run_classify(str(ROOT / "examples/tickets/phishing.json"), SETTINGS, llm)
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out.split("\n\nattempts")[0])["category"] == "security_incident"
    assert "security_terms" in out  # added by code
    assert "attempts: 1" in out and "cost: $" in out


async def test_missing_file_is_a_clean_error(capsys):
    assert await run_classify("nope.json", SETTINGS, FakeLLM([])) == 2
    assert "Cannot read" in capsys.readouterr().err


async def test_invalid_ticket_is_a_clean_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"id": "X", "subject": "s", "body": "   ", "requester_id": "u-1"}')
    assert await run_classify(str(bad), SETTINGS, FakeLLM([])) == 2
    assert "not a valid ticket" in capsys.readouterr().err


async def test_failed_classification_returns_1(capsys):
    llm = FakeLLM([forced_tool_response("submit_classification", {})] * 3)
    assert await run_classify(str(ROOT / "examples/tickets/vague.json"), SETTINGS, llm) == 1
    assert "CLASSIFICATION FAILED" in capsys.readouterr().err


def test_argument_parsing_requires_a_command(capsys):
    try:
        main([])
    except SystemExit as exc:
        assert exc.code == 2
