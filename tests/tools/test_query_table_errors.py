"""
Error-path tests for query_table — Phase 3 Wave 0 stub.

Covers:
- QUERY-05 / QUERY-06: unknown_column on filter column, sort column, columns param
- invalid_filter_op for unsupported / malformed op input
- invalid_cursor (Plan 03-03 dependency — stays RED until 03-03 ships)

Function-body imports of `query_table` keep collection successful until
Plan 03-02 ships `mcp_zeeker.tools.retrieval`.
"""

from __future__ import annotations

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
    """pdpc with enforcement_decisions; `id` is in HIDDEN_COLUMNS['*']."""
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
async def datasette_client(httpx_mock: pytest_httpx.HTTPXMock):
    async with httpx.AsyncClient(base_url=config.UPSTREAM_URL) as http:
        dc = DatasetteClient(http)
        token = DatasetteClient.bind(dc)
        yield dc
        DatasetteClient.reset(token)


@pytest.fixture
async def metadata_cache(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(url=_metadata_url(), json={"databases": {}}, is_reusable=True)
    async with httpx.AsyncClient(base_url=config.UPSTREAM_URL) as http:
        mc = MetadataCache(http, config.UPSTREAM_URL, ttl=0)
        token = MetadataCache.bind(mc)
        yield mc
        MetadataCache.reset(token)
        MetadataCache.clear_singleton()


async def test_unknown_column_in_filter(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-05: nonexistent filter column raises ToolError(unknown_column)."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload())

    with pytest.raises(ToolError, match="unknown_column"):
        await query_table(
            "pdpc",
            "enforcement_decisions",
            filters=[{"column": "does_not_exist", "op": "exact", "value": "x"}],
        )


async def test_unknown_column_hidden_filter(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-06: hidden column 'id' raises unknown_column — same code path as nonexistent."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload())

    with pytest.raises(ToolError, match="unknown_column"):
        await query_table(
            "pdpc",
            "enforcement_decisions",
            filters=[{"column": "id", "op": "exact", "value": "1"}],
        )


async def test_unknown_column_in_sort(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-05: nonexistent sort column raises unknown_column."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload())

    with pytest.raises(ToolError, match="unknown_column"):
        await query_table("pdpc", "enforcement_decisions", sort="does_not_exist")


async def test_unknown_column_in_columns_param(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-05: nonexistent column in `columns=` raises unknown_column."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload())

    with pytest.raises(ToolError, match="unknown_column"):
        await query_table("pdpc", "enforcement_decisions", columns=["does_not_exist"])


async def test_invalid_filter_op_unsupported(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D3-02: ops outside the 13-string FilterOp Literal are rejected by pydantic."""
    from fastmcp.exceptions import ToolError
    from pydantic import ValidationError

    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload())

    # Pydantic ValidationError or wrapped ToolError(invalid_filter_op)
    with pytest.raises((ValidationError, ToolError)):
        await query_table(
            "pdpc",
            "enforcement_decisions",
            filters=[{"column": "title", "op": "regex", "value": ".*"}],
        )


async def test_invalid_cursor_shape_mismatch(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """D3-03: cursor produced for shape A rejected when reused with shape B.

    This stays RED until Plan 03-03 ships cursor encode/decode wired into
    query_table. Function-body import keeps collection successful.
    """
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(url=_zeeker_schemas_url("pdpc"), json=_empty_schema_payload())

    with pytest.raises(ToolError, match="invalid_cursor"):
        await query_table(
            "pdpc",
            "enforcement_decisions",
            cursor="zzzzzzz-shape-mismatch-token",
        )
