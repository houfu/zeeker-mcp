"""
Unit tests for fetch tool handler — Phase 3 Plan 03-04 (Slice C, URL-keyed fetch).

Covers (per 03-VALIDATION.md):
- FETCH-01: happy path — fetch by URL on zeeker-judgements.judgments returns one row
- FETCH-02: exact-match — `?utm=...` query-string variant misses (not_found)
- FETCH-03: heavy columns + FK + hidden columns stripped from response;
            fetch NEVER emits a `retrieved_content` key (use query_table on the
            matching *_fragments table for paragraph-level content)
- FETCH-04: unsupported_table_for_fetch on a table without URL_COLUMNS mapping;
            no upstream table-row request is issued
- FETCH-05: not_found on zero-row response + INJ-05 (URL is NOT echoed in the
            error message or in any log record)
- D3-14 step 6 multi-match: when upstream returns ≥2 rows, fetch returns the
            FIRST row + emits a structured WARNING `event=fetch_ambiguous_url`
            whose record MUST NOT contain the URL (INJ-05)
- unknown_database / unknown_table propagate from _resolve_table (same shape as
            query_table; counter-patch test in test_retrieval_side_channel.py
            already proves single-emission identity for hidden vs nonexistent)
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
    """Canonical /zeeker-judgements.json payload for fetch tests.

    Contains:
    - `judgments` (URL-keyed via URL_COLUMNS[zeeker-judgements.judgments]=source_url)
      with a heavy text column `content_text`, a heavy `html_raw`, a globally-hidden
      `id`, and a hand-rolled `judgment_id` to exercise FK / hidden-column stripping.
    - `ad_hoc_synthetic_table` — visible upstream but absent from URL_COLUMNS,
      used by the FETCH-04 unsupported_table_for_fetch case.
    """
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
    """A single-row /-/json response for the canonical judgment URL.

    Includes `id` (globally hidden), `content_text` and `html_raw` (heavy) so
    tests can assert the strip pass excludes all three from the envelope.
    """
    return {
        "rows": [
            {
                "id": 1,
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
            "id",
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


async def test_fetch_known_judgment_returns_one_row(
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
    row = envelope.data[0]
    # All non-heavy non-hidden columns present
    assert row["citation"] == "2026 SGDC 136"
    assert row["source_url"] == JUDGMENT_URL


async def test_fetch_exact_match_only_no_normalization(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """FETCH-02: ?utm=… variant is a different exact string — not_found (no silent match)."""
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


async def test_fetch_unsupported_table(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """FETCH-04: table without URL_COLUMNS mapping raises unsupported_table_for_fetch.

    Also asserts no upstream table-row request is issued: only the /-/db.json summary
    call required by _resolve_table fires before the helper raises.
    """
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

    # No table-row upstream call should have been issued (D3-14 step 2 short-circuit).
    table_url = _table_url("zeeker-judgements", "ad_hoc_synthetic_table")
    table_requests = [r for r in httpx_mock.get_requests() if str(r.url).startswith(table_url)]
    assert table_requests == [], f"Unexpected upstream request to {table_url}: {table_requests}"


async def test_fetch_not_found_zero_rows(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock, caplog
) -> None:
    """FETCH-05 / INJ-05: not_found message MUST NOT echo the URL — also assert log silence."""
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
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ToolError) as exc_info:
            await fetch("zeeker-judgements", "judgments", url=hostile_url)

    msg = str(exc_info.value)
    assert "not_found" in msg
    # The URL substring MUST NOT appear in the error message (INJ-05)
    assert "SECRET-PATH-CANARY-9999" not in msg
    assert "example.com" not in msg
    # And the URL MUST NOT leak into any log record either
    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRET-PATH-CANARY-9999" not in log_text
    assert "example.com" not in log_text


async def test_fetch_strips_heavy_and_fragment_columns(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """FETCH-03: heavy columns + globally hidden columns are stripped from the envelope.

    Per the plan's <behavior> step 7, fetch reshapes the row using:
      emit_cols = (visible - HEAVY_COLUMNS) - fk_to_exclude
    where `visible` is _visible_columns() (which already excludes hidden columns
    like the global `id`). HEAVY_COLUMNS (content_text, html_raw, …) are dropped
    entirely; fetch never emits a `retrieved_content` key — callers wanting
    heavy text should use query_table on the matching *_fragments table.
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
    httpx_mock.add_response(
        url=_table_url("zeeker-judgements", "judgments"),
        json=_single_judgment_row(),
        is_reusable=True,
    )

    envelope = await fetch("zeeker-judgements", "judgments", url=JUDGMENT_URL)
    row = envelope.data[0]

    # No heavy column inlined (D3-19 snapshot, FETCH-03)
    assert set(row.keys()) & config.HEAVY_COLUMNS == set()
    # `retrieved_content` MUST NOT appear in fetch responses (must_have line + FETCH-03)
    assert "retrieved_content" not in row
    # Globally-hidden `id` is stripped via _visible_columns (HIDDEN_COLUMNS["*"])
    assert "id" not in row
    # Light columns still present
    assert "citation" in row
    assert "source_url" in row


async def test_fetch_ambiguous_url_returns_first_and_warns(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock, caplog
) -> None:
    """D3-14 step 6: upstream returns ≥2 rows → return FIRST + WARN; URL NOT logged.

    INJ-05: the structured WARNING record `event=fetch_ambiguous_url` MUST NOT
    contain the URL substring in any rendered form. The handler binds only
    `database`, `table`, and `match_count` to the record.
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
            "id": 2,
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

    # First row only
    assert len(envelope.data) == 1
    assert envelope.data[0]["citation"] == "2026 SGDC 136"

    # The URL itself MUST NOT appear in any log record (INJ-05)
    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "elitigation" not in log_text
    assert JUDGMENT_URL not in log_text
    # A `fetch_ambiguous_url` event must have been emitted with match_count=2.
    # structlog renders kwargs into the JSON message string under the configured
    # JSONRenderer; assert against the message body for both substrings.
    ambiguous_records = [r for r in caplog.records if "fetch_ambiguous_url" in r.getMessage()]
    assert ambiguous_records, "expected a WARNING with event=fetch_ambiguous_url"
    rendered = ambiguous_records[0].getMessage()
    assert (
        '"match_count": 2' in rendered
        or "'match_count': 2" in rendered
        or "match_count=2" in rendered
    )


async def test_fetch_unknown_database(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """unknown_database routes through _resolve_table (shared with query_table)."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import fetch

    with pytest.raises(ToolError, match="unknown_database"):
        await fetch("nonexistent-db", "judgments", url=JUDGMENT_URL)


async def test_fetch_unknown_table(
    datasette_client, metadata_cache, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    """unknown_table routes through _resolve_table (hidden + nonexistent share one code path)."""
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import fetch

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"), json=_judgments_db_payload(), is_reusable=True
    )

    with pytest.raises(ToolError, match="unknown_table"):
        await fetch("zeeker-judgements", "totally_fictitious_table", url="https://example.com/x")
