"""
Unit tests for fetch tool handler — Phase 3 Wave 0 stub.

Covers (per 03-VALIDATION.md):
- FETCH-01: happy path — fetch by URL on zeeker-judgements.judgments returns one row
- FETCH-02: exact-match — `?utm=...` query-string variant misses (not_found)
- FETCH-03: D3-19 snapshot — heavy columns do NOT inline; they live under retrieved_content
- FETCH-04: unsupported_table_for_fetch on a table without URL_COLUMNS mapping
- FETCH-05: not_found on zero-row response + structlog warning (no URL echo)

All tests use function-body imports of `fetch` so collection succeeds until
Plan 03-04 ships `fetch` in `mcp_zeeker.tools.retrieval`.
"""

from __future__ import annotations

import logging

import httpx
import pytest
import pytest_httpx

from mcp_zeeker import config
from mcp_zeeker.core.datasette_client import DatasetteClient
from mcp_zeeker.core.metadata_cache import MetadataCache

JUDGMENT_URL = "https://www.elitigation.sg/gd/s/2026_SGDC_136"


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
                    "source_url",
                    "summary",
                    "content_text",
                    "html_raw",
                ],
                "primary_keys": ["id"],
            },
            {
                # synthetic table without URL_COLUMNS mapping (FETCH-04 fixture)
                "name": "ad_hoc_synthetic_table",
                "hidden": False,
                "count": 0,
                "columns": ["foo", "bar"],
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


def _single_judgment_row() -> dict:
    return {
        "rows": [
            {
                "citation": "2026 SGDC 136",
                "case_name": "Re Foo",
                "decision_date": "2026-03-01",
                "source_url": JUDGMENT_URL,
                "summary": "stub",
                "content_text": "long body of the judgment",
                "html_raw": "<p>long body</p>",
            }
        ],
        "columns": [
            "citation",
            "case_name",
            "decision_date",
            "source_url",
            "summary",
            "content_text",
            "html_raw",
        ],
        "next": None,
        "truncated": False,
        "filtered_table_rows_count": 1,
    }


def _no_rows_payload() -> dict:
    return {
        "rows": [],
        "columns": ["citation", "source_url"],
        "next": None,
        "truncated": False,
        "filtered_table_rows_count": 0,
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


async def test_fetch_happy_path_returns_single_row(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """FETCH-01: fetch on zeeker-judgements.judgments with a known URL returns one row."""
    from mcp_zeeker.tools.retrieval import fetch

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"),
        json=_empty_schema_payload(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"),
        json=_single_judgment_row(),
        is_reusable=True,
    )

    envelope = await fetch("zeeker-judgements", "judgments", url=JUDGMENT_URL)
    assert len(envelope.data) == 1


async def test_fetch_exact_match_utm_variant_misses(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """FETCH-02: ?utm=… variant is a different exact string — not_found."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import fetch

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"),
        json=_empty_schema_payload(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"),
        json=_no_rows_payload(),
        is_reusable=True,
    )

    with pytest.raises(ToolError, match="not_found"):
        await fetch(
            "zeeker-judgements",
            "judgments",
            url=JUDGMENT_URL + "?utm_source=share",
        )


async def test_fetch_heavy_columns_under_retrieved_content(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """FETCH-03 / D3-19: heavy columns do NOT inline; they live under retrieved_content."""
    from mcp_zeeker.tools.retrieval import fetch

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"),
        json=_empty_schema_payload(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"),
        json=_single_judgment_row(),
        is_reusable=True,
    )

    envelope = await fetch("zeeker-judgements", "judgments", url=JUDGMENT_URL)
    row = envelope.data[0]
    # No heavy column inlined
    assert set(row.keys()) & config.HEAVY_COLUMNS == set()
    # retrieved_content keys are a subset of HEAVY_COLUMNS (D3-19)
    assert "retrieved_content" in row
    assert set(row["retrieved_content"].keys()) <= config.HEAVY_COLUMNS


async def test_fetch_unsupported_table_for_fetch(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """FETCH-04: table without URL_COLUMNS mapping raises unsupported_table_for_fetch."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import fetch

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )

    with pytest.raises(ToolError, match="unsupported_table_for_fetch"):
        await fetch(
            "zeeker-judgements",
            "ad_hoc_synthetic_table",
            url="https://example.com/x",
        )


async def test_fetch_not_found_does_not_echo_url(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock, caplog
) -> None:
    """FETCH-05 / INJ-05: not_found error message MUST NOT echo the URL."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import fetch

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"),
        json=_empty_schema_payload(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"),
        json=_no_rows_payload(),
        is_reusable=True,
    )

    hostile_url = "https://example.com/SECRET-PATH-CANARY-9999"
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ToolError) as exc_info:
            await fetch("zeeker-judgements", "judgments", url=hostile_url)

    msg = str(exc_info.value)
    assert "not_found" in msg
    assert "SECRET-PATH-CANARY-9999" not in msg
    # Also assert the URL doesn't leak into the log stream
    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRET-PATH-CANARY-9999" not in log_text


async def test_fetch_multi_match_returns_first_and_warns(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock, caplog
) -> None:
    """D3-14 step 6: when upstream returns 2+ rows, fetch returns first + warns.

    The warning record MUST NOT echo the URL (INJ-05). Will RED until Plan 03-04
    wires the multi-match warning into fetch.
    """
    from mcp_zeeker.tools.retrieval import fetch

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"),
        json=_empty_schema_payload(),
        is_reusable=True,
    )
    # Build a two-row response
    two_rows = _single_judgment_row()
    two_rows["rows"].append(
        {
            "citation": "2026 SGDC 137",
            "case_name": "Re Bar",
            "decision_date": "2026-03-02",
            "source_url": JUDGMENT_URL,
            "summary": "second match",
            "content_text": "another body",
            "html_raw": "<p>another body</p>",
        }
    )
    two_rows["filtered_table_rows_count"] = 2
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"),
        json=two_rows,
        is_reusable=True,
    )

    with caplog.at_level(logging.WARNING):
        envelope = await fetch("zeeker-judgements", "judgments", url=JUDGMENT_URL)

    assert len(envelope.data) == 1  # first row only
    # The url itself MUST NOT appear in any log record
    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "elitigation" not in log_text
