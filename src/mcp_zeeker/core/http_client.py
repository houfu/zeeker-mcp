# src/mcp_zeeker/core/http_client.py
# Source: 01-PATTERNS.md "src/mcp_zeeker/core/http_client.py" section
# (extracted from Pattern A lines 247–258)
from __future__ import annotations

import httpx

from mcp_zeeker import config


def build_http_client() -> httpx.AsyncClient:
    """Single factory so tests can swap it for an ASGITransport-backed client."""
    return httpx.AsyncClient(
        base_url=config.UPSTREAM_URL,
        timeout=httpx.Timeout(connect=1.0, read=10.0, write=2.0, pool=2.0),
        limits=httpx.Limits(
            # 100 > soak concurrency (50) to absorb fan-out: search fans out to
            # N databases per call, so one MCP request can hold multiple upstream
            # connections simultaneously. At concurrency=50 with 20% search, the
            # fan-out alone can saturate a pool of 50, causing PoolTimeout → 502.
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        ),
        headers={"User-Agent": config.USER_AGENT},
    )
