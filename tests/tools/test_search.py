"""
Handler-level tests for the cross-DB search tool — Wave 0 stub (Plan 04-01).

Tests the @mcp.tool `search` handler shipped in Plan 04-02. Each test:
- Stubs the 4 upstream /{db}.json responses (auto-discovery shape).
- Stubs per-table /{db}/{table}.json?_search=... responses via regex matcher
  (the `_search=` query string makes plain-URL matching impractical — Phase 3
  uses the same regex matcher pattern, paste-verified).
- Asserts the envelope's preview-row shape (D4-21), heavy-column absence
  (D3-19 / D4-12), multi-DB provenance (D4-16), and pagination
  `upstream_total_hits` population (D4-17).

Wave 0 RED stub: imports `from mcp_zeeker.tools.search import search` INSIDE
the function body so collection succeeds before Plan 04-02 ships the handler.
Tests use `pytest.skip(...)` so the runner stays clean until Plan 04-02 fills
in the bodies.
"""

from __future__ import annotations

import re

import httpx
import pytest
import pytest_httpx

from mcp_zeeker import config
from mcp_zeeker.core.datasette_client import DatasetteClient


def _table_url_re(database: str, table: str) -> re.Pattern[str]:
    """Regex matcher for /{database}/{table}.json with any query string.

    pytest_httpx 0.36 matches `add_response(url=str)` on the FULL URL
    (including query params). Since search always issues `_search=...`,
    a bare-URL string would require enumerating every query-string variant.
    The regex matches the path regardless of query string.
    """
    base = re.escape(config.UPSTREAM_URL.rstrip("/"))
    return re.compile(rf"^{base}/{re.escape(database)}/{re.escape(table)}\.json(\?.*)?$")


@pytest.fixture
async def datasette_client(httpx_mock: pytest_httpx.HTTPXMock):
    """Local DatasetteClient bound to current context (mirror Phase 3 fixture)."""
    async with httpx.AsyncClient(base_url=config.UPSTREAM_URL) as http:
        dc = DatasetteClient(http)
        token = DatasetteClient.bind(dc)
        yield dc
        DatasetteClient.reset(token)


async def test_default_databases_searches_all_four(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """SEARCH-02 / D4-10: `search(query="x")` with no `databases` arg dispatches
    per-table FTS for all 4 ALLOWED_DATABASES (pdpc naturally returns 0 because
    it has no FTS — auto-discovery filters it out).
    """
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    # ruff: noqa - body kept as guidance for Plan 04-02
    from mcp_zeeker.tools.search import search  # noqa: F401 — Plan 04-02 imports at body level


async def test_preview_shape_uniform(datasette_client, httpx_mock: pytest_httpx.HTTPXMock) -> None:
    """SEARCH-04 / D4-21: every row in envelope.data has exactly the 6 preview keys."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_no_heavy_columns_in_preview(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D3-19 / D4-12: heavy columns NEVER appear in preview rows.

    Stubs upstream rows including `content_text` (a HEAVY_COLUMNS member)
    and asserts `set(row.keys()) & config.HEAVY_COLUMNS == set()` for every row.
    """
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_envelope_provenance_for_search(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-16: envelope.provenance.database is None, .table is None,
    .license == LICENSE_MIXED (multi-DB scope)."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_upstream_total_hits_populated(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-17: envelope.pagination.upstream_total_hits is keyed `<db>.<table>`
    and populated from each per-table `filtered_table_rows_count`."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_no_site_wide_search_dispatched(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-18 / 04-RESEARCH §3.2 Pitfall 3: handler NEVER hits /-/search.json
    (Datasette's all-table fuzzy endpoint) — only per-table FTS via the
    fts_table-not-null discovery gate."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from mcp_zeeker.tools.search import search  # noqa: F401


async def test_limit_one_returns_exactly_one(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """SEARCH-02 / D4-11: `limit=1` returns exactly one row regardless of how many
    tables matched (round-robin merge per D4-05 stops at limit)."""
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    from mcp_zeeker.tools.search import search  # noqa: F401
