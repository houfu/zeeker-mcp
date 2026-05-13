"""
Counter-patch tests for column visibility — Phase 3 Wave 0 stub (D3-07).

Mirrors `tests/tools/test_discovery_side_channel.py` (DISC-05 counter pattern)
at the column level. Proves CODE-PATH IDENTITY between hidden columns and
nonexistent columns: both must invoke `raise_unknown_column` exactly once
each — no presence side-channel.

D3-07 scope: three handler paths route through raise_unknown_column —
filters column, sort column, columns parameter. All three are asserted here.

Function-body imports of `query_table` keep collection successful until
Plan 03-02 ships `mcp_zeeker.tools.retrieval`.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import pytest_httpx

from mcp_zeeker import config
from mcp_zeeker.core.datasette_client import DatasetteClient
from mcp_zeeker.core.metadata_cache import MetadataCache


def _db_url(name: str) -> str:
    base = config.UPSTREAM_URL.rstrip("/")
    return f"{base}/{name}.json"


def _zeeker_schemas_url(db: str) -> str:
    base = config.UPSTREAM_URL.rstrip("/")
    return f"{base}/{db}/_zeeker_schemas.json"


def _metadata_url() -> str:
    return f"{config.UPSTREAM_URL}/-/metadata.json"


def _pdpc_db_payload() -> dict:
    """pdpc.enforcement_decisions; global-hidden 'id' present in upstream columns."""
    return {
        "tables": [
            {
                "name": "enforcement_decisions",
                "hidden": False,
                "count": 100,
                "columns": [
                    "id",
                    "title",
                    "organisation",
                    "decision_type",
                    "decision_date",
                    "decision_url",
                    "penalty_amount",
                    "summary",
                ],
                "primary_keys": [],
            },
        ]
    }


def _empty_schema_payload() -> dict:
    return {
        "columns": [
            "resource_name",
            "schema_version",
            "schema_hash",
            "column_definitions",
            "created_at",
            "updated_at",
        ],
        "rows": [],
    }


@pytest.fixture
def datasette_client(httpx_mock: pytest_httpx.HTTPXMock):
    http = httpx.AsyncClient(base_url=config.UPSTREAM_URL)
    dc = DatasetteClient(http)
    token = DatasetteClient.bind(dc)
    yield dc
    DatasetteClient.reset(token)


@pytest.fixture
def metadata_cache(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(url=_metadata_url(), json={"databases": {}}, is_reusable=True)
    mc = MetadataCache(httpx.AsyncClient(base_url=config.UPSTREAM_URL), config.UPSTREAM_URL, ttl=0)
    token = MetadataCache.bind(mc)
    yield mc
    MetadataCache.reset(token)
    MetadataCache.clear_singleton()


async def test_filter_column_routes_through_raise_unknown_column(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D3-07: filter on hidden + nonexistent column each invoke raise_unknown_column once."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.core.visibility import raise_unknown_column
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(
        url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload(), is_reusable=True
    )

    counter = {"n": 0}
    original_raise = raise_unknown_column

    def counting_raise(database: str, table: str, column: str) -> None:
        counter["n"] += 1
        original_raise(database, table, column)

    # Patch at the retrieval call-site (NOT the visibility module — patch where
    # query_table LOOKS UP raise_unknown_column).
    with patch("mcp_zeeker.tools.retrieval.raise_unknown_column", counting_raise):
        with pytest.raises(ToolError):
            await query_table(
                "pdpc",
                "enforcement_decisions",
                filters=[{"column": "id", "op": "exact", "value": "x"}],  # hidden
            )
        with pytest.raises(ToolError):
            await query_table(
                "pdpc",
                "enforcement_decisions",
                filters=[{"column": "does_not_exist", "op": "exact", "value": "x"}],  # absent
            )

    assert counter["n"] == 2, f"Expected 2 raise_unknown_column calls, got {counter['n']}"


async def test_sort_column_routes_through_raise_unknown_column(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D3-07: sort on hidden + nonexistent column each invoke raise_unknown_column once."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.core.visibility import raise_unknown_column
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(
        url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload(), is_reusable=True
    )

    counter = {"n": 0}
    original_raise = raise_unknown_column

    def counting_raise(database: str, table: str, column: str) -> None:
        counter["n"] += 1
        original_raise(database, table, column)

    with patch("mcp_zeeker.tools.retrieval.raise_unknown_column", counting_raise):
        with pytest.raises(ToolError):
            await query_table("pdpc", "enforcement_decisions", sort="id")  # hidden
        with pytest.raises(ToolError):
            await query_table("pdpc", "enforcement_decisions", sort="does_not_exist")  # absent

    assert counter["n"] == 2


async def test_columns_param_routes_through_raise_unknown_column(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D3-07: columns= with hidden + nonexistent each invoke raise_unknown_column once."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.core.visibility import raise_unknown_column
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(
        url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload(), is_reusable=True
    )

    counter = {"n": 0}
    original_raise = raise_unknown_column

    def counting_raise(database: str, table: str, column: str) -> None:
        counter["n"] += 1
        original_raise(database, table, column)

    with patch("mcp_zeeker.tools.retrieval.raise_unknown_column", counting_raise):
        with pytest.raises(ToolError):
            await query_table(
                "pdpc",
                "enforcement_decisions",
                columns=["id"],  # hidden
            )
        with pytest.raises(ToolError):
            await query_table(
                "pdpc",
                "enforcement_decisions",
                columns=["does_not_exist"],  # absent
            )

    assert counter["n"] == 2


async def test_no_zeeker_schemas_call_on_unknown_column(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D3-07: unknown_column error path makes no upstream _zeeker_schemas call.

    The handler must reject the column reference BEFORE fetching column types.
    """
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)

    with pytest.raises(ToolError):
        await query_table(
            "pdpc",
            "enforcement_decisions",
            filters=[{"column": "id", "op": "exact", "value": "x"}],
        )

    zeeker_schema_reqs = [r for r in httpx_mock.get_requests() if "_zeeker_schemas" in str(r.url)]
    assert len(zeeker_schema_reqs) == 0
