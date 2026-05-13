"""
Wave-0 stub for TRANSPORT-01, TRANSPORT-02, TRANSPORT-03; implemented in plan 05.

Tests:
- Server accepts connections at /mcp via streamable HTTP transport.
- initialize handshake completes over real uvicorn random-port HTTP.
- Server is stateless: two independent sessions work correctly.
"""

import pytest


def test_streamable_http_transport():
    """TRANSPORT-01: /mcp accepts POST and GET via streamable HTTP transport."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
    # Will use: from mcp.client.streamable_http import streamablehttp_client
    # Will use: from mcp.client.session import ClientSession
    # Will use: uvicorn on a random port


def test_initialize_over_http():
    """TRANSPORT-02: initialize handshake completes over real HTTP."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_stateless_session():
    """TRANSPORT-03: Server is stateless; two independent sessions work correctly."""
    pytest.skip("Wave 0 stub — implemented in plan 05")


def test_two_independent_sessions():
    """TRANSPORT-03: Two simultaneous clients receive independent responses."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
