"""
Error-path tests for cross-DB search — Wave 0 stub (Plan 04-01).

Tests every error branch in the search handler against the LOCKED Phase 4
error catalog (D3-12 / WR-02 / D4-09):
  - invalid_query  — empty/whitespace query, limit OOR, all-tables-400
  - unknown_database — databases=["not_a_db"]
  - upstream_unavailable — every per-table call fails with non-400 status

All-tables-400 promotion (04-RESEARCH §3.7 / D4-09 case c): when EVERY
per-table FTS call returns HTTP 400 (the captured
`zeeker_judgements__judgments__fts_error.json` body), the handler maps this
to `invalid_query` instead of `upstream_unavailable`. This is the defensive
catch for an FTS5 syntax error that escape_fts5 somehow missed — extremely
unlikely in practice but the safety net is required by D4-09.

Phase 2 LEARNING (`is_reusable=True` teardown trap): for these transient-
failure tests, ALWAYS use EXPLICIT ORDERED `add_response()` calls, NOT
`is_reusable=True`. The retry path (D-16: one retry on 502/503) makes
reusable-response timing brittle.

Wave 0 RED stub: each test uses `pytest.skip` until Plan 04-02 wires the
handler body. Imports happen inside the function bodies.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_httpx

from mcp_zeeker import config
from mcp_zeeker.core.datasette_client import DatasetteClient


@pytest.fixture
async def datasette_client(httpx_mock: pytest_httpx.HTTPXMock):
    async with httpx.AsyncClient(base_url=config.UPSTREAM_URL) as http:
        dc = DatasetteClient(http)
        token = DatasetteClient.bind(dc)
        yield dc
        DatasetteClient.reset(token)


async def test_empty_query_invalid_query(datasette_client) -> None:
    """D4-09 case (a) / D4-19 step 1: empty string → invalid_query."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_whitespace_query_invalid_query(datasette_client) -> None:
    """D4-09 case (a) / D4-19 step 1: whitespace-only string → invalid_query."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_limit_zero_invalid_query(datasette_client) -> None:
    """D4-09 case (b) / D4-11: limit=0 from a direct caller bypassing
    Pydantic's `ge=1` clamp → invalid_query (belt-and-suspenders)."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_limit_above_max_invalid_query(datasette_client) -> None:
    """D4-09 case (b) / D4-11: limit=101 → invalid_query (max is 100)."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_unknown_database(datasette_client) -> None:
    """D4-10: `databases=["nonexistent"]` raises ToolError("unknown_database: ...").

    Uses the existing raise_unknown_database helper (Phase 1).
    """
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_all_tables_400_invalid_query(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-09 case (c) / 04-RESEARCH §3.7: every per-table FTS call returns
    HTTP 400 → invalid_query.

    Stubs each searchable table for zeeker-judgements with status_code=400 and
    the captured `zeeker_judgements__judgments__fts_error.json` body. Uses
    EXPLICIT ORDERED add_response calls (NO is_reusable=True per Phase 2
    LEARNING — the retry-once path makes reusable-response timing brittle).
    """
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_all_tables_500_upstream_unavailable(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-09 / 04-RESEARCH §3.7: every per-table FTS call returns HTTP 500
    → upstream_unavailable (NOT invalid_query — only the all-400 path promotes).
    """
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401
