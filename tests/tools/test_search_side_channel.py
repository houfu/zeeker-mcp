"""
Counter-patch tests for sole-emission helpers in search — Wave 0 stub (04-01).

Mirrors `tests/tools/test_retrieval_side_channel.py` pattern at the search
handler level. Proves CODE-PATH IDENTITY: every `invalid_query` trigger
routes through the SAME `raise_invalid_query` helper — no inline ToolError
strings.

The patch target is `mcp_zeeker.tools.search.raise_invalid_query` (NOT the
visibility module) because Python's `unittest.mock.patch` rewrites the
binding at the import site. The handler imports `raise_invalid_query`
from core.visibility into its own module namespace, and that namespace is
where the function name is looked up at call time.

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


async def test_invalid_query_single_emission(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-09 / WR-02: every invalid_query path goes through `raise_invalid_query`.

    Counter-patches `mcp_zeeker.tools.search.raise_invalid_query` and asserts
    the counter increments exactly 4 times for the 4 trigger paths:
      1. query=""           — D4-19 step 1 empty-query guard
      2. query="   "        — same guard (strip())
      3. limit=0            — D4-11 belt-and-suspenders
      4. limit=101          — D4-11 belt-and-suspenders

    The unittest.mock.patch target is the IMPORT-SITE binding (the handler
    module's local namespace), NOT core.visibility — see test_retrieval_side_channel
    lines 136-140 for the same discipline.
    """
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from unittest.mock import patch  # noqa: F401

    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.core.visibility import raise_invalid_query  # noqa: F401
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_no_preview_columns_log_emitted(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """CONTEXT line 338 / D4-12: searchable_tables_for emits a structured
    `search_table_no_preview_columns` warning when a discovered FTS-indexed
    table fails resolve_preview_columns.

    Stub a DB whose only table has fts_table=non-null but columns matching
    NO preview defaults (e.g. {"weird_col_1", "weird_col_2"}). Counter-patch
    the structlog warning emitter and assert it was invoked with
    `event=search_table_no_preview_columns` and bindings exposing
    `database` + `table` only (NEVER the query string — INJ-05 / D4-07).
    """
    pytest.skip("RED until Plan 04-02 ships searchable_tables_for body")
    from unittest.mock import patch  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401
