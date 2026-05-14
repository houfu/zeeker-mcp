"""
Orchestrator tests for fan_out_search — Wave 0 stub (Plan 04-01).

Tests `mcp_zeeker.core.search.fan_out_search` (Plan 04-02's body):
  1. test_round_robin_merge — merge order interleaves rounds across tables (D4-05).
  2. test_exhausted_table_skipped — tables with fewer rows are skipped silently.
  3. test_partial_failure — one table 500s, the other succeeds: failed_tables=1.
  4. test_all_fail_returns_zero_rows — every table 500s: zero rows, full failure count.
  5. test_upstream_total_hits_aggregated — per-table `filtered_table_rows_count`
     surfaced verbatim into the returned dict.

Phase 2 LEARNING: for `test_partial_failure`, use EXPLICIT ORDERED
`httpx_mock.add_response` calls — NOT `is_reusable=True`. The retry-once
path (D-16) makes reusable-response timing brittle.

Wave 0 RED stub: each test uses `pytest.skip` until Plan 04-02 ships
fan_out_search body. Imports `from mcp_zeeker.core.search import fan_out_search`
inside the function bodies.
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


async def test_round_robin_merge(datasette_client, httpx_mock: pytest_httpx.HTTPXMock) -> None:
    """D4-05: merge order interleaves rounds across all target tables.

    Stub 2 tables under one DB, each returning 3 rows. Call
    fan_out_search(escaped_query, target_tables, per_table_limit=3) and
    assert returned-rows order is `[t1_r1, t2_r1, t1_r2, t2_r2, t1_r3, t2_r3]`.
    """
    pytest.skip("RED until Plan 04-02 ships fan_out_search body")
    from mcp_zeeker.core.search import fan_out_search  # noqa: F401


async def test_exhausted_table_skipped(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-05: exhausted tables skipped silently after their last row.

    Table t1 returns 1 row; t2 returns 3 rows. Assert merge order
    `[t1_r1, t2_r1, t2_r2, t2_r3]`.
    """
    pytest.skip("RED until Plan 04-02 ships fan_out_search body")
    from mcp_zeeker.core.search import fan_out_search  # noqa: F401


async def test_partial_failure(datasette_client, httpx_mock: pytest_httpx.HTTPXMock) -> None:
    """D4-07 / D-16: partial failure surfaces as failed_tables count.

    Table 1 returns 500 (both initial + retry per D-16; use EXPLICIT ORDERED
    add_response — NO is_reusable=True). Table 2 succeeds. Assert:
      - returned `failed_tables == 1`
      - `upstream_total_hits` does NOT contain a key for table 1
      - merged rows contain only rows from table 2

    Plan 04-02's fan_out_search returns a 4-tuple ending in `failure_statuses`
    (list[int|None]) — table 1's failure should appear as `500` in that list.
    """
    pytest.skip("RED until Plan 04-02 ships fan_out_search body")
    from mcp_zeeker.core.search import fan_out_search  # noqa: F401


async def test_all_fail_returns_zero_rows(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-07: every table 500s → zero rows, full failure count.

    Stub every table with status_code=500 (explicit ordered add_response).
    Assert:
      - returned rows == []
      - returned upstream_total_hits == {}
      - returned failed_tables == len(target_tables)
      - returned failure_statuses is a list of 500s
    """
    pytest.skip("RED until Plan 04-02 ships fan_out_search body")
    from mcp_zeeker.core.search import fan_out_search  # noqa: F401


async def test_upstream_total_hits_aggregated(
    datasette_client, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D4-17: per-table `filtered_table_rows_count` surfaced verbatim.

    Stub two tables with `filtered_table_rows_count` = 7 and 42 respectively.
    Assert `upstream_total_hits == {"db.t1": 7, "db.t2": 42}` after
    fan_out_search returns.
    """
    pytest.skip("RED until Plan 04-02 ships fan_out_search body")
    from mcp_zeeker.core.search import fan_out_search  # noqa: F401
