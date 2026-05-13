"""
Wave-0 stub for ANNO-02 (INJ-01); implemented in plan 05.

Tests:
- Every registered tool description ends with config.TOOL_TRAILER verbatim.

Note: Per 01-PATTERNS.md, this file is a thin redirect. The primary test lives in
test_envelope_contract.py::test_every_registered_tool_description_ends_with_trailer.

"""

import pytest


def test_tool_trailer_present():
    """ANNO-02 / INJ-01: Every registered tool description ends with TOOL_TRAILER verbatim."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
    # Will use: from mcp_zeeker.server import mcp
    # Will use: from mcp_zeeker import config
