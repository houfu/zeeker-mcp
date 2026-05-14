"""
D6.1-03 / Finding #4 — live regression for heavy-column query on
sg-gov-newsrooms.*_news tables.

The manual UAT (06.1-CONTEXT.md Finding #4) caught that
`query_table(database="sg-gov-newsrooms", table="mlaw_news",
columns=["content_text"], limit=1)` returned `upstream_unavailable` while
the light projection on the same table succeeded.

Root cause: upstream Datasette has `mlaw_news` configured with a default
sort on `published_date` (table-level metadata directive). When the
connector sent `_col=content_text&_size=1` WITHOUT including
`published_date` in `_col=`, Datasette generated invalid SQL referencing
the implicit ORDER BY column and returned HTTP 400 "Invalid SQL:
incomplete input". The connector retry path then surfaced
`upstream_unavailable` to the caller.

Fix: `query_table` now sets `_sort=rowid` whenever the caller does not
specify a sort, which overrides Datasette's per-table implicit sort with
the rowid order — uniform across every table, no behavioral change on
tables without an implicit sort.

This live-gated test exercises the fix end-to-end against the production
upstream so any future regression in URL construction (or in Datasette's
upstream metadata configuration) re-trips the gate.

Gate: `ZEEKER_LIVE=1` (registered via `tests/conftest.py
pytest_collection_modifyitems`). The test auto-skips otherwise.

Operating model: this test does NOT use the `mcp_client` fixture (which
wires the in-memory FastMCP Client against `mcp` directly and so does not
bind the production lifespan that wires DatasetteClient and MetadataCache).
Instead it constructs and binds those caches manually pointing at
`config.UPSTREAM_URL` (default `https://data.zeeker.sg` in production; can
be overridden via the `UPSTREAM_URL` env var for staging probes) and
invokes the `query_table` handler directly as a Python function.
"""

from __future__ import annotations

import httpx
import pytest

from mcp_zeeker import config
from mcp_zeeker.core.datasette_client import DatasetteClient
from mcp_zeeker.core.fragment_join import ParentPKCache
from mcp_zeeker.core.metadata_cache import MetadataCache
from mcp_zeeker.core.middleware.retrieved_at import tool_started_at
from mcp_zeeker.tools.retrieval import query_table


@pytest.mark.live
async def test_mlaw_news_heavy_column_returns_content() -> None:
    """`query_table(sg-gov-newsrooms, mlaw_news, columns=["content_text"])`
    returns a row with `retrieved_content.content_text` populated AND a
    `_policy` block — NOT `upstream_unavailable`.

    Requires ZEEKER_LIVE=1.
    """
    from datetime import UTC, datetime

    async with httpx.AsyncClient(base_url=config.UPSTREAM_URL) as http:
        dc_token = DatasetteClient.bind(DatasetteClient(http))
        mc_token = MetadataCache.bind(
            MetadataCache(http, config.UPSTREAM_URL, ttl=config.METADATA_TTL_SECONDS)
        )
        pk_token = ParentPKCache.bind(ParentPKCache())
        # Bind tool_started_at so synthesize_citation has a deterministic
        # retrieved_at — outside the FastMCP middleware seam.
        rt_token = tool_started_at.set(datetime(2026, 1, 1, tzinfo=UTC))
        try:
            envelope = await query_table(
                database="sg-gov-newsrooms",
                table="mlaw_news",
                columns=["content_text"],
                limit=1,
            )
        finally:
            tool_started_at.reset(rt_token)
            ParentPKCache.reset(pk_token)
            MetadataCache.reset(mc_token)
            DatasetteClient.reset(dc_token)
            MetadataCache.clear_singleton()
            DatasetteClient.clear_singleton()
            ParentPKCache.clear_singleton()

    rows = envelope.data
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"

    retrieved = rows[0].get("retrieved_content")
    assert retrieved is not None, (
        f"retrieved_content missing — heavy column projection failed: {rows[0]!r}"
    )

    content_text = retrieved.get("content_text")
    assert content_text, f"content_text empty or missing: {retrieved!r}"
    assert isinstance(content_text, str), (
        f"content_text not a string: {type(content_text).__name__}"
    )

    policy = retrieved.get("_policy")
    assert policy is not None, f"_policy missing from retrieved_content: {retrieved!r}"

    # Operator-locked policy values per config.CONTENT_POLICIES for
    # sg-gov-newsrooms.mlaw_news (Singapore Open Data Licence v1.0, allowed).
    expected_policy = config.CONTENT_POLICIES[("sg-gov-newsrooms", "mlaw_news")]
    assert policy == expected_policy, (
        f"_policy mismatch.\n  expected: {expected_policy!r}\n  got:      {policy!r}"
    )
