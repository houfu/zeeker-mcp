"""
Shared test fixtures for the mcp-zeeker test suite.

Live fixtures replacing the Wave-0 stubs. Provides:
- mcp_client: FastMCP in-memory client (async context manager)
- asgi_client: httpx.AsyncClient backed by ASGITransport
- stub_upstream: pre-registers the 4 upstream DB responses via httpx_mock
- live_server: random-port uvicorn server in a daemon thread (Pattern C)
- _free_port: OS-assigned free port helper
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import pytest_httpx
import uvicorn
from fastmcp import Client

from mcp_zeeker import config
from mcp_zeeker.app import app
from mcp_zeeker.core.datasette_client import DatasetteClient
from mcp_zeeker.server import mcp


def _free_port() -> int:
    """Bind to port 0 to get an OS-assigned free port, then release the socket."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def live_server():
    """Spawn uvicorn on a random port in a daemon thread; yield the /mcp/ URL.

    The thread is cleaned up after each test. The server uses asyncio loop so
    pytest-httpx patches (which also use asyncio) are visible in the thread.

    Moved from tests/test_mcp_streamable_smoke.py to conftest.py (Phase 2 Plan 03)
    so that F-3 stateless-session tests can share the same fixture.
    """
    port = _free_port()
    cfg = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(cfg)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Poll until the server is ready (up to 2.5s)
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "uvicorn did not start within 2.5s"
    yield f"http://127.0.0.1:{port}/mcp/"
    server.should_exit = True
    thread.join(timeout=5)


def _db_url(name: str) -> str:
    """Build the full upstream URL for a given DB name."""
    base = config.UPSTREAM_URL.rstrip("/")
    return f"{base}/{name}.json"


def _tables_payload(names: list[str]) -> dict:
    """Build a minimal Datasette /{db}.json payload."""
    return {"tables": [{"name": n} for n in names]}


@pytest.fixture
async def mcp_client():
    """
    Async fixture yielding a FastMCP in-memory client bound to the MCP app.

    The context manager entry triggers the MCP initialize handshake automatically.
    """
    async with Client(mcp) as c:
        yield c


@pytest.fixture
async def asgi_client():
    """
    Async fixture yielding an httpx.AsyncClient backed by ASGITransport(app).

    Uses the real Starlette app (including all middleware). Suitable for
    testing /healthz and the Origin allowlist without a live server.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.fixture
def stub_upstream(httpx_mock: pytest_httpx.HTTPXMock):
    """
    Pre-register the four upstream /{db}.json responses.

    sglawwatch gets 4 tables (2 hidden + 2 visible); all other DBs get 2 tables.
    Returns the httpx_mock fixture for further customization by individual tests.
    """
    for db in config.ALLOWED_DATABASES:
        if db == "sglawwatch":
            tables = ["metadata", "schema_versions", "t1", "t2"]
        else:
            tables = ["t1", "t2"]
        httpx_mock.add_response(
            url=_db_url(db),
            json=_tables_payload(tables),
        )
    return httpx_mock


@pytest.fixture
def bound_datasette_client(stub_upstream):
    """
    Bind a DatasetteClient backed by a real httpx.AsyncClient to the current context.

    The stub_upstream fixture is depended on to ensure upstream calls are intercepted.
    Tears down the binding on fixture teardown.
    """
    http = httpx.AsyncClient(base_url=config.UPSTREAM_URL)
    dc = DatasetteClient(http)
    token = DatasetteClient.bind(dc)
    yield dc
    DatasetteClient.reset(token)
