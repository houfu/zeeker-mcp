"""
Shared test fixtures for the mcp-zeeker test suite.

Wave-0 scaffolding: fixtures are stubs. Plans 04/05 will populate them with
real mcp_client and asgi_client implementations.
"""

import pytest


@pytest.fixture
async def mcp_client():
    """
    Async fixture yielding a FastMCP in-memory client bound to the MCP app.

    Wave-0 stub: implemented in plan 04/05.
    """
    pytest.skip("Wave 0 stub — implemented in plan 04/05")
    yield  # unreachable; satisfies async generator shape


@pytest.fixture
async def asgi_client():
    """
    Async fixture yielding an httpx.AsyncClient backed by ASGITransport(app).

    Wave-0 stub: implemented in plan 05.
    """
    pytest.skip("Wave 0 stub — implemented in plan 05")
    yield  # unreachable; satisfies async generator shape
