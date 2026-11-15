"""Shared pytest fixtures (extended on Day 5 with fakes)."""

import pytest

from mcp_servers.common import reset_faults


@pytest.fixture(autouse=True)
def _clean_fault_injection(monkeypatch):
    """No test may inherit a FAULT_INJECT setting, and TIMEOUT_ONCE state never leaks."""
    monkeypatch.delenv("FAULT_INJECT", raising=False)
    reset_faults()
    yield
    reset_faults()
