"""
Auto-discovery semantics tests for cross-DB search — Wave 0 stub (Plan 04-01).

Tests the FOUR-gate filter in `core.search.searchable_tables_for`:
  1. `fts_table is not None` — LOAD-BEARING safety gate (Pitfall 3).
  2. Table is in `_visible_tables(db)` — Phase 2 hidden-flag + HIDDEN_TABLES.
  3. Table name does NOT end with `_fragments` (SEARCH_DENYLIST_PATTERNS).
  4. `resolve_preview_columns` returns non-null title AND url (D4-12).

Most important assertion: pdpc.enforcement_decisions is NEVER dispatched to
because it has NO `fts_table` upstream (04-RESEARCH §3.2 / Probe 2). The
captured `pdpc__enforcement_decisions__search_ignored.json` fixture shows
Datasette silently returning rowid-ordered rows — without the safety gate
these would surface as fake "search results."

Wave 0 RED stub: each test uses `pytest.skip` until Plan 04-02 wires the
handler + searchable_tables_for body.
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


async def test_fts_gate_drops_non_fts_table(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-02 gate 1: tables with `fts_table=None` are dropped from dispatch.

    Stub a DB with 3 tables:
      - `fts_yes` — fts_table set, has matching preview columns
      - `fts_no` — fts_table=None (no FTS index)
      - `fts_hidden` — fts_table set BUT marked hidden=true upstream
    Assert: only `fts_yes` appears in upstream_total_hits.
    """
    pytest.skip("RED until Plan 04-02 ships searchable_tables_for + handler bodies")
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_fragments_excluded_via_denylist(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-04 gate 3: tables ending in `_fragments` are denylisted.

    Stub a DB with `t1` and `t1_fragments` — both have fts_table set, both
    have matching preview columns. Assert only `t1` is dispatched to;
    `t1_fragments` filtered out via SEARCH_DENYLIST_PATTERNS suffix match.
    """
    pytest.skip("RED until Plan 04-02 ships searchable_tables_for + handler bodies")
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_pdpc_no_dispatch(datasette_client, httpx_mock: pytest_httpx.HTTPXMock) -> None:
    """04-RESEARCH §3.2 / Pitfall 3 / T-04-04: pdpc never gets `_search=` calls.

    The captured `pdpc__enforcement_decisions__search_ignored.json` fixture
    proves that when `_search=` is sent to a non-FTS table, Datasette silently
    returns rowid-ordered rows (fake "search results"). The fts_table-not-null
    gate prevents this — assert NO httpx request URL contains
    `/pdpc/enforcement_decisions.json?_search=`.

    Pattern mirrors tests/tools/test_discovery_side_channel.py lines 113-140
    (no-upstream-call assertion via httpx_mock.get_requests()).
    """
    pytest.skip("RED until Plan 04-02 ships searchable_tables_for + handler bodies")
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_no_preview_columns_drops_table(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-12 gate 4: tables whose columns match no preview default are dropped.

    Stub a DB with one table that has fts_table set but columns =
    {"some_weird_col", "another_one"} — none of the SEARCH_PREVIEW_DEFAULTS
    candidates match. Assert the table is not in upstream_total_hits.keys()
    (searchable_tables_for logs `search_table_no_preview_columns` and skips).
    """
    pytest.skip("RED until Plan 04-02 ships searchable_tables_for + handler bodies")
    from mcp_zeeker.tools.search import search  # noqa: F401
