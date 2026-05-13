"""
Wave-0 stub for TRANSPORT-01, TRANSPORT-02, TRANSPORT-04, ANNO-01, ANNO-03, DISC-01;
implemented in plan 05.

Tests:
- initialize handshake completes; serverInfo.name non-empty.
- tools/list returns flat type:object (no anyOf/oneOf/allOf at top level).
- list_databases tool carries required annotations.
- list_databases returns 4 configured DBs.
"""

import pytest


def test_initialize_handshake():
    """TRANSPORT-01 / TRANSPORT-02: initialize handshake completes via in-memory client."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
    # Will use: from fastmcp import Client
    # Will use: from mcp_zeeker.server import mcp


def test_tools_list_flat_schema():
    """TRANSPORT-04: tools/list returns flat type:object schema (no anyOf/oneOf/allOf)."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_tool_annotations():
    """ANNO-01: list_databases carries readOnlyHint, idempotentHint, openWorldHint all True."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_inputschema_is_flat():
    """TRANSPORT-04: Input schema is flat type:object with no nesting."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_list_databases_returns_four_dbs():
    """DISC-01: list_databases returns exactly 4 databases."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
