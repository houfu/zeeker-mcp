"""
Wave-0 stub for CFG-01, CFG-02; implemented in plan 02.

Tests:
- config.py is single source of truth for all constants.
- All required keys are present in config.py.
- TOOL_TRAILER matches PRD §10 sentence verbatim.
- ALLOWED_DATABASES contains exactly the 4 configured databases.
"""

import pytest


def test_single_source_of_truth():
    """CFG-01: All denylists/allowlists/constants live in config.py."""
    pytest.skip("Wave 0 stub — implemented in plan 02")
    # Will use: from mcp_zeeker import config


def test_constants_present():
    """CFG-02: Required keys present in config.py."""
    pytest.skip("Wave 0 stub — implemented in plan 02")
    # Will check: LOG_FIELDS, ALLOWED_DATABASES, HIDDEN_TABLES, TOOL_TRAILER,
    #             ALLOWED_ORIGINS, LICENSE_MIXED, LICENSES, UPSTREAM_URL, USER_AGENT


def test_allowed_databases():
    """CFG-01: ALLOWED_DATABASES contains the 4 Singapore legal databases."""
    pytest.skip("Wave 0 stub — implemented in plan 02")
    # Will assert: config.ALLOWED_DATABASES == (
    #     "zeeker-judgements", "pdpc", "sg-gov-newsrooms", "sglawwatch"
    # )


def test_tool_trailer_verbatim():
    """CFG-01: TOOL_TRAILER matches PRD §10 sentence verbatim."""
    pytest.skip("Wave 0 stub — implemented in plan 02")
    # Will assert exact text from PRD §10
