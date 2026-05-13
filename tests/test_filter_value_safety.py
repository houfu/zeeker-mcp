"""
Hostile-input canary corpus — Phase 3 Wave 0 stub (D3-09 / INJ-05 / QUERY-09).

This is a STUB pointing at Plan 03-02's query_table handler. The 5-canary
minimum corpus (D3-09) drives a parametrized test that asserts the canary
NEVER appears in:
- the ToolError message
- captured stdout / stderr
- the structlog log stream

Function-body imports of `query_table` keep collection successful until
03-02 ships the handler — at which point this entire file goes GREEN.

The 5-canary minimum (D3-09):
1. HTML/system-tag injection sentinel
2. FTS5-operator-bearing string
3. 5 KB string (oversized payload)
4. plain canary token (round-trip detector)
5. malformed UTF-8 byte sequence (decode error path)
"""

from __future__ import annotations

import logging

import httpx
import pytest
import pytest_httpx

from mcp_zeeker import config
from mcp_zeeker.core.datasette_client import DatasetteClient
from mcp_zeeker.core.metadata_cache import MetadataCache

CANARY_STRINGS = [
    "</system>",  # HTML/system tag injection sentinel
    "NEAR('data' 'protection') AND NOT",  # FTS5 operators (would error if forwarded)
    "x" * 5001,  # 5 KB oversized string
    "ZEEKER_CANARY_42",  # plain round-trip detector
    b"\xff\xfe".decode("utf-8", errors="replace"),  # malformed UTF-8 (replaced)
]


def _db_url(name: str) -> str:
    base = config.UPSTREAM_URL.rstrip("/")
    return f"{base}/{name}.json"


def _zeeker_schemas_url(db: str) -> str:
    base = config.UPSTREAM_URL.rstrip("/")
    return f"{base}/{db}/_zeeker_schemas.json"


def _metadata_url() -> str:
    return f"{config.UPSTREAM_URL}/-/metadata.json"


def _pdpc_db_payload() -> dict:
    return {
        "tables": [
            {
                "name": "enforcement_decisions",
                "hidden": False,
                "count": 100,
                "columns": [
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


@pytest.mark.parametrize("canary", CANARY_STRINGS)
async def test_filter_value_never_echoed_in_error_or_log(
    datasette_client,
    metadata_cache,
    httpx_mock: pytest_httpx.HTTPXMock,
    caplog,
    capsys,
    canary: str,
) -> None:
    """D3-09 / INJ-05: hostile filter values MUST NOT appear in any output channel.

    Will RED until Plan 03-02 ships query_table. Function-body import keeps
    collection successful for the whole Wave 0 stub set.
    """
    # Function-body import — module doesn't exist yet
    from fastmcp.exceptions import ToolError

    from mcp_zeeker.tools.retrieval import query_table

    httpx_mock.add_response(url=_db_url("pdpc"), json=_pdpc_db_payload(), is_reusable=True)
    httpx_mock.add_response(
        url=_zeeker_schemas_url("pdpc"),
        json={
            "columns": [
                "resource_name",
                "schema_version",
                "schema_hash",
                "column_definitions",
                "created_at",
                "updated_at",
            ],
            "rows": [],
        },
        is_reusable=True,
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ToolError) as exc_info:
            await query_table(
                "pdpc",
                "enforcement_decisions",
                filters=[
                    {"column": "organisation", "op": "gt", "value": canary}
                ],  # gt on TEXT column should fail coercion or be permitted by Datasette;
                #   regardless, the canary must not surface in any error message.
            )

    captured = capsys.readouterr()
    log_text = " ".join(r.getMessage() for r in caplog.records)
    error_text = str(exc_info.value)

    for surface_name, surface_text in (
        ("stdout", captured.out),
        ("stderr", captured.err),
        ("log", log_text),
        ("error", error_text),
    ):
        assert canary not in surface_text, f"Canary leaked into {surface_name}: {canary[:40]}..."
