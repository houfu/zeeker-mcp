"""
Unit tests for query_table tool handler — Phase 3 Wave 0 stub.

Covers (per 03-VALIDATION.md):
- QUERY-01: rows returned with envelope (light projection by default)
- QUERY-02: light columns only when no `columns=` is passed
- QUERY-03: heavy text columns surface under `retrieved_content` when opted in
- QUERY-07: limit defaults to 50, max 200; 201 rejected by pydantic
- Sort ascending / descending (`-col` prefix)
- contains is case-insensitive (SQLite LIKE — ASCII)

All tests use function-body imports of `query_table` so collection succeeds
until Plan 03-02 ships `mcp_zeeker.tools.retrieval`.
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


def _table_url(database: str, table: str) -> str:
    base = config.UPSTREAM_URL.rstrip("/")
    return f"{base}/{database}/{table}.json"


def _metadata_url() -> str:
    return f"{config.UPSTREAM_URL}/-/metadata.json"


def _judgments_db_payload() -> dict:
    return {
        "tables": [
            {
                "name": "judgments",
                "hidden": False,
                "count": 100,
                "columns": [
                    "id",
                    "citation",
                    "case_name",
                    "decision_date",
                    "court",
                    "source_url",
                    "summary",
                    "content_text",
                    "html_raw",
                ],
                "primary_keys": ["id"],
            },
        ]
    }


def _judgments_rows_payload(rows: list[dict] | None = None) -> dict:
    return {
        "rows": rows
        or [
            {
                "citation": "2026 SGDC 136",
                "case_name": "Test v Test",
                "decision_date": "2026-01-01",
                "court": "SGDC",
                "source_url": "https://example.com/x",
                "summary": "stub",
            }
        ],
        "columns": ["citation", "case_name", "decision_date", "court", "source_url", "summary"],
        "next": None,
        "truncated": False,
        "filtered_table_rows_count": 1,
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


async def test_default_light_columns_only(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-02 / D3-04: default response excludes heavy text columns."""
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"), json=_empty_schema_payload()
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"), json=_judgments_rows_payload()
    )

    envelope = await query_table("zeeker-judgements", "judgments")
    for row in envelope.data:
        assert set(row.keys()) & config.HEAVY_COLUMNS == set()
        assert "rowid" not in row


async def test_heavy_columns_under_retrieved_content(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-03 / D3-04: heavy text columns surface under retrieved_content when opted in."""
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"), json=_empty_schema_payload()
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"),
        json={
            "rows": [{"citation": "2026 SGDC 136", "content_text": "long body"}],
            "columns": ["citation", "content_text"],
            "next": None,
            "truncated": False,
            "filtered_table_rows_count": 1,
        },
    )

    envelope = await query_table(
        "zeeker-judgements", "judgments", columns=["citation", "content_text"]
    )
    for row in envelope.data:
        assert "content_text" not in row
        assert "retrieved_content" in row
        assert "content_text" in row["retrieved_content"]
        # D3-19: retrieved_content keys are exactly the heavy subset
        assert set(row["retrieved_content"].keys()) <= config.HEAVY_COLUMNS


async def test_limit_max_200_accepted(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-07: limit=200 (MAX_QUERY_LIMIT) is accepted by pydantic."""
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"), json=_empty_schema_payload()
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"), json=_judgments_rows_payload()
    )

    # Should not raise
    envelope = await query_table("zeeker-judgements", "judgments", limit=200)
    assert envelope is not None


async def test_limit_201_rejected_by_pydantic(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-07: limit=201 exceeds MAX_QUERY_LIMIT (200) — Pydantic clamp rejects."""
    from fastmcp.exceptions import ToolError
    from pydantic import ValidationError

    from mcp_zeeker.tools.retrieval import query_table

    # FastMCP may wrap pydantic ValidationError as ToolError; accept either path.
    with pytest.raises((ValidationError, ToolError)):
        await query_table("zeeker-judgements", "judgments", limit=201)


async def test_sort_ascending(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-01: sort by ascending column issues _sort=col to upstream."""
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"), json=_empty_schema_payload()
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"), json=_judgments_rows_payload()
    )

    envelope = await query_table("zeeker-judgements", "judgments", sort="decision_date")
    assert envelope is not None
    # Spot-check upstream request had _sort param
    table_reqs = [r for r in httpx_mock.get_requests() if "judgments.json" in str(r.url)]
    assert any("_sort=decision_date" in str(r.url) for r in table_reqs)


async def test_sort_descending_via_dash_prefix(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-01: sort prefix '-' issues _sort_desc to upstream."""
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"), json=_empty_schema_payload()
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"), json=_judgments_rows_payload()
    )

    envelope = await query_table("zeeker-judgements", "judgments", sort="-decision_date")
    assert envelope is not None
    table_reqs = [r for r in httpx_mock.get_requests() if "judgments.json" in str(r.url)]
    assert any("_sort_desc=decision_date" in str(r.url) for r in table_reqs)


async def test_filter_contains_case_insensitive(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """QUERY-01 / D3-02: contains compiles to __contains (SQLite LIKE — case-insensitive ASCII)."""
    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"), json=_empty_schema_payload()
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"), json=_judgments_rows_payload()
    )

    envelope = await query_table(
        "zeeker-judgements",
        "judgments",
        filters=[{"column": "case_name", "op": "contains", "value": "test"}],
    )
    assert envelope is not None
    table_reqs = [r for r in httpx_mock.get_requests() if "judgments.json" in str(r.url)]
    assert any("case_name__contains" in str(r.url) for r in table_reqs)
