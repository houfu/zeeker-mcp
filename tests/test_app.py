"""
Wave-0 stub for TRANSPORT-03, TRANSPORT-06; implemented in plan 05.

Tests:
- /healthz returns {"status": "ok"} without making upstream calls.
- Origin allowlist matrix: missing Origin ALLOW, allowlisted ALLOW, foreign DENY 403.
- OPTIONS preflight with allowlisted Origin returns 204 with CORS headers.
"""

import pytest


def test_healthz_returns_ok_without_upstream():
    """OBS-01 / TRANSPORT-06: /healthz returns ok without upstream call."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
    # Will use: from mcp_zeeker.app import app
    # Will use: httpx.AsyncClient(transport=httpx.ASGITransport(app))


def test_origin_missing_allowed():
    """TRANSPORT-06: Missing Origin header is allowed (Claude clients call server-side)."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_origin_allowlisted_allowed():
    """TRANSPORT-06: Allowlisted Origin (https://claude.ai) is allowed."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_origin_foreign_rejected_403():
    """TRANSPORT-06: Foreign Origin (https://evil.example.com) is rejected with 403."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_origin_preflight_options_allowed():
    """TRANSPORT-06: OPTIONS preflight with allowlisted Origin returns 204 with CORS headers."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_origin_allowlist():
    """TRANSPORT-06: Origin allowlist matrix — all cases pass."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
