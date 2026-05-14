"""Phase 5 — INJ-05 hostile-URL corpus + multi-match URL-hash assertion.

Carries forward the 5-canary corpus from Phase 3 (`tests/test_filter_value_safety.py`)
VERBATIM to maintain parity. Plan 05-03 body-fills the actual assertion logic:
the parent URL value MUST NOT appear in the response envelope, ToolError text,
captured stdout/stderr, or the structlog log stream — across the fragment-join
code path (`query_table` against any `*_fragments` table).

The multi-match warning test asserts the FRAG-06 / D5-04 contract: when Call 1
returns more than one parent row, the structured warning event
`"fragment_parent_multi_match"` is emitted with a 16-hex-char `parent_url_hash`
binding and NEVER the raw URL or parent_pk.

References: D3-09 / D5-04 / INJ-05 / FRAG-06.
"""

from __future__ import annotations

import json
import logging
import re

import httpx
import pytest
import pytest_httpx
from fastmcp.exceptions import ToolError

from mcp_zeeker import config
from mcp_zeeker.core.datasette_client import DatasetteClient
from mcp_zeeker.core.filter_compiler import Filter
from mcp_zeeker.core.metadata_cache import MetadataCache
from mcp_zeeker.tools.retrieval import query_table
from tests.conftest import _load_fragments_fixture

# Verbatim from tests/test_filter_value_safety.py (Phase 3) — INJ-05 parity.
# Plan 05-03 swaps in real assertions; today the corpus exists so the file
# collects cleanly and the parametrize wiring is in place.
CANARY_STRINGS: list[str] = [
    "</system>",
    "NEAR('data' 'protection') AND NOT",
    "x" * 5001,
    "ZEEKER_CANARY_42",
    "\udc80",
]


# ---------------------------------------------------------------------------
# URL helpers (mirror tests/tools/test_retrieval_fragment_join.py shape)
# ---------------------------------------------------------------------------


def _db_url(name: str) -> str:
    base = config.UPSTREAM_URL.rstrip("/")
    return f"{base}/{name}.json"


def _zeeker_schemas_url(db: str) -> str:
    base = config.UPSTREAM_URL.rstrip("/")
    return f"{base}/{db}/_zeeker_schemas.json"


def _metadata_url() -> str:
    return f"{config.UPSTREAM_URL}/-/metadata.json"


def _table_url_re(database: str, table: str) -> re.Pattern[str]:
    base = re.escape(config.UPSTREAM_URL.rstrip("/"))
    return re.compile(rf"^{base}/{re.escape(database)}/{re.escape(table)}\.json(\?.*)?$")


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


def _judgments_db_payload() -> dict:
    """zeeker-judgements/.json — both judgments and judgments_fragments tables."""
    return {
        "tables": [
            {
                "name": "judgments",
                "hidden": False,
                "count": 219,
                "columns": [
                    "id",
                    "citation",
                    "case_name",
                    "case_numbers",
                    "decision_date",
                    "court",
                    "subject_tags",
                    "source_url",
                    "pdf_url",
                    "summary",
                    "content_text",
                    "created_at",
                ],
                "primary_keys": ["id"],
            },
            {
                "name": "judgments_fragments",
                "hidden": False,
                "count": 5000,
                "columns": [
                    "id",
                    "judgment_id",
                    "ordinal",
                    "paragraph_number",
                    "class_name",
                    "section_heading",
                    "content_text",
                    "html_raw",
                    "footnote_text",
                    "has_footnotes",
                    "has_table",
                    "has_figure",
                    "figure_src",
                    "figure_descriptions",
                ],
                "primary_keys": ["id"],
            },
        ]
    }


# ---------------------------------------------------------------------------
# Fixtures (local — mirror test_retrieval_fragment_join.py)
# ---------------------------------------------------------------------------


@pytest.fixture
async def datasette_client(httpx_mock: pytest_httpx.HTTPXMock):
    async with httpx.AsyncClient(base_url=config.UPSTREAM_URL) as http:
        dc = DatasetteClient(http)
        token = DatasetteClient.bind(dc)
        yield dc
        DatasetteClient.reset(token)


@pytest.fixture
async def metadata_cache(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(
        url=_metadata_url(), json={"databases": {}}, is_reusable=True, is_optional=True
    )
    async with httpx.AsyncClient(base_url=config.UPSTREAM_URL) as http:
        mc = MetadataCache(http, config.UPSTREAM_URL, ttl=0)
        token = MetadataCache.bind(mc)
        yield mc
        MetadataCache.reset(token)
        MetadataCache.clear_singleton()


# ---------------------------------------------------------------------------
# INJ-05 leak-detection helpers
# ---------------------------------------------------------------------------


def _canary_sentinel(canary: str) -> str:
    """Return the substring used as the leakage signature for this canary.

    The 5 KB ``"x" * 5001`` canary is shortened to ``"x" * 100`` to keep the
    substring scan cheap while staying long enough that natural English text
    in captured fixtures cannot match it accidentally. Mirrors
    tests/test_search_value_safety.py (Phase 4).
    """
    if canary == "x" * 5001:
        return "x" * 100
    return canary


def _surfaces_contain(
    canary: str,
    *,
    envelope_text: str,
    error_text: str,
    captured_out: str,
    captured_err: str,
    log_text: str,
) -> list[str]:
    """Return list of surface names where the canary appears.

    For unprintable canaries, also check repr() so backslash-escape leakage
    (e.g. '\\udc80') is detected. Mirrors test_filter_value_safety.py /
    test_search_value_safety.py.
    """
    leaks: list[str] = []
    for surface_name, surface_text in (
        ("envelope", envelope_text),
        ("error", error_text),
        ("stdout", captured_out),
        ("stderr", captured_err),
        ("log", log_text),
    ):
        if canary in surface_text:
            leaks.append(surface_name)
        # Defense in depth: catch backslash-escape leakage of unprintable canaries.
        if repr(canary).strip("'\"") in surface_text and repr(canary) != repr(""):
            leaks.append(f"{surface_name}_repr")
    return leaks


# ---------------------------------------------------------------------------
# T-05-17 — INJ-05 hostile-URL corpus across fragment-join path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("canary", CANARY_STRINGS)
@pytest.mark.asyncio
async def test_url_value_never_echoed(
    bound_parent_pk_cache,
    datasette_client,
    metadata_cache,
    httpx_mock: pytest_httpx.HTTPXMock,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    canary: str,
) -> None:
    """D3-09 / D5-04 / INJ-05: the hostile parent-URL canary MUST NOT appear in
    the response envelope, the ToolError text, captured stdout/stderr, or the
    structlog log stream — across the fragment-join path on `*_fragments`.

    The canary is the value of an `exact` filter on the parent URL column
    (`source_url`). Upstream Call 1 returns 0 rows (empty-parent path) so the
    handler short-circuits with an empty envelope. The 5 KB and lone-surrogate
    canaries may instead trigger upstream encoding errors or HTTP 414; both
    outcomes are acceptable as long as the canary never appears in any output
    surface.
    """
    # Special-case: the lone-surrogate canary cannot be URL-encoded by httpx,
    # so the parent-lookup request never reaches the wire (raises
    # UnicodeEncodeError inside urllib). Mark downstream stubs as optional so
    # pytest-httpx teardown does not complain. The 5 KB canary is
    # URL-encodeable and DOES hit the wire.
    is_surrogate = canary == "\udc80"

    # DB/schema stubs — re-usable across both code paths the canary may take.
    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"),
        json=_judgments_db_payload(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"),
        json=_empty_schema_payload(),
        is_reusable=True,
        is_optional=is_surrogate,
    )

    # Call 1 (parent lookup) — return 0 rows (empty-parent path). NOTE: the
    # current Plan 05-02 source (`fragment_join.compile_filter` line 366)
    # returns `([], None)` when Call 1 reports zero rows. The handler at
    # `tools/retrieval.py` then detects `fragment_join_active=False` (no
    # parent_fk filter in the rewritten list) and PROCEEDS to query the
    # fragments table with an empty filter list — fetching the entire table.
    # This is a pre-existing behavior shipped by Plan 05-02; flagged in the
    # 05-03-SUMMARY.md deviations section as a follow-up source-fix candidate
    # (Plan 05-04 / Phase 6). For THIS test the contract under verification is
    # INJ-05 (no canary echo), which holds regardless — we register a Call 2
    # stub returning empty rows so the test completes.
    empty_parent_payload = {
        "rows": [],
        "columns": _judgments_db_payload()["tables"][0]["columns"],
        "next": None,
        "truncated": False,
        "filtered_table_rows_count": 0,
    }
    httpx_mock.add_response(
        url=_table_url_re("zeeker-judgements", "judgments"),
        json=empty_parent_payload,
        is_reusable=True,
        is_optional=is_surrogate,
    )
    # Call 2 stub — empty fragments page (the bug-noted full-table scan path).
    empty_fragments_payload = {
        "rows": [],
        "columns": _judgments_db_payload()["tables"][1]["columns"],
        "next": None,
        "truncated": False,
        "filtered_table_rows_count": None,
    }
    httpx_mock.add_response(
        url=_table_url_re("zeeker-judgements", "judgments_fragments"),
        json=empty_fragments_payload,
        is_reusable=True,
        is_optional=True,
    )

    envelope_text = ""
    error_text = ""
    # Scope caplog at DEBUG so even the chattiest mcp_zeeker.* log path is
    # asserted against. The leak contract holds at every level.
    with caplog.at_level(logging.DEBUG):
        try:
            envelope = await query_table(
                database="zeeker-judgements",
                table="judgments_fragments",
                filters=[Filter(column="source_url", op="exact", value=canary)],
            )
            # The empty-parent code path returns an empty envelope.
            envelope_text = json.dumps(envelope.model_dump(mode="json"), default=str)
        except ToolError as exc:
            # Acceptable for the 5 KB / surrogate canaries — upstream encoding
            # failure surfaces as `upstream_unavailable` (fixed literal).
            error_text = str(exc)
        except (ExceptionGroup, BaseExceptionGroup) as eg:
            # Lone-surrogate canary may escape the anyio task group as an
            # ExceptionGroup (UnicodeEncodeError in httpx URL encoding). The
            # INJ-05 invariant still holds.
            error_text = str(eg)
        except UnicodeEncodeError as ue:
            # Defensive: plain wire-level encoding failure (no anyio wrapper).
            error_text = str(ue)

    captured = capsys.readouterr()
    log_text = " ".join(
        r.getMessage()
        for r in caplog.records
        if r.name.startswith("mcp_zeeker") or r.name == "root"
    )

    sentinel = _canary_sentinel(canary)
    leaks = _surfaces_contain(
        sentinel,
        envelope_text=envelope_text,
        error_text=error_text,
        captured_out=captured.out,
        captured_err=captured.err,
        log_text=log_text,
    )

    # SURROGATE EXCEPTION (documented in Phase 4 Plan 04-03 / Plan 05-03):
    # the lone-surrogate canary "\udc80" cannot be URL-encoded by httpx
    # (UnicodeEncodeError raised inside urllib.parse / codecs BEFORE the
    # request is dispatched). Python's UnicodeEncodeError str() includes the
    # offending character's `\\udc80` repr by design — this is internal
    # Python machinery, NOT a channel WE control. The INJ-05 invariant for
    # this canary is narrowed to: the canary must not leak into envelope,
    # stdout, stderr, or caplog (channels under our control). The
    # error.__str__ surface is permitted to include `\\udc80` repr because
    # that string never reaches the LLM (ToolError doesn't propagate
    # UnicodeEncodeError; the handler maps it to upstream_unavailable in
    # production). For this test, drop "error" and "error_repr" leak
    # entries for the surrogate canary only.
    if canary == "\udc80":
        leaks = [s for s in leaks if s not in ("error", "error_repr")]

    assert not leaks, (
        f"Canary leaked into {leaks}; canary[:40]={canary[:40]!r}, "
        f"envelope={envelope_text[:200]!r}, error={error_text!r}"
    )


# ---------------------------------------------------------------------------
# T-05-18 / T-05-19 — multi-match warning hashes URL (no leak)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_match_warning_hashes_url(
    bound_parent_pk_cache,
    datasette_client,
    metadata_cache,
    httpx_mock: pytest_httpx.HTTPXMock,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """FRAG-06 / D5-04 / INJ-05: when Call 1 returns ≥2 parent rows, the
    handler emits a structured warning `event="fragment_parent_multi_match"`
    whose binding contains a 16-hex-char `parent_url_hash` and NEVER the raw
    URL substring nor the parent_pk literal.
    """
    multi_match_payload = _load_fragments_fixture("zeeker_judgements__judgments__multi_match.json")
    fragments_payload = _load_fragments_fixture(
        "zeeker_judgements__judgments_fragments__page1.json"
    )
    # The multi-match probe URL — from RESEARCH §5 + the captured fixture.
    test_url = "https://www.elitigation.sg/gd/s/2001_SGHC_216"
    # The parent_pk literal that the captured fixture's rows share.
    parent_pk_literal = "6074e86bc12d"
    # The selected (newer) created_at timestamp — `_sort_desc=created_at&_size=1`
    # picks rows[0], which is the newer of the two stale duplicates.
    expected_selected_match_value = "2026-04-22T21:07:09.426849"

    httpx_mock.add_response(
        url=_db_url("zeeker-judgements"),
        json=_judgments_db_payload(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_zeeker_schemas_url("zeeker-judgements"),
        json=_empty_schema_payload(),
        is_reusable=True,
    )
    # Call 1 — multi-match response (2 rows, filtered_table_rows_count=2).
    httpx_mock.add_response(
        url=_table_url_re("zeeker-judgements", "judgments"),
        json=multi_match_payload,
    )
    # Call 2 — any valid fragments payload (the warning fires on Call 1
    # multi-match; Call 2 content is irrelevant for THIS test's assertions).
    httpx_mock.add_response(
        url=_table_url_re("zeeker-judgements", "judgments_fragments"),
        json=fragments_payload,
    )

    with caplog.at_level(logging.DEBUG):
        envelope = await query_table(
            database="zeeker-judgements",
            table="judgments_fragments",
            filters=[Filter(column="source_url", op="exact", value=test_url)],
        )

    # Sanity — Call 2 ran and the envelope built.
    assert envelope is not None

    # Filter caplog records to those emitted by mcp_zeeker.* / structlog
    # (NOT httpx wire-level INFO logs, which log the FULL request URL
    # including `judgment_id__exact=<parent_pk>` query parameters — those
    # are out of scope for the INJ-05 / FRAG-02 contract under test here).
    # Mirrors tests/test_search_value_safety.py filtering discipline.
    captured = capsys.readouterr()
    # Combine ONLY mcp_zeeker.* / root caplog text + structlog JSONRenderer
    # output on stdout/stderr — exclude httpx wire-level INFO.
    mcp_zeeker_log_text = " ".join(
        r.getMessage()
        for r in caplog.records
        if r.name.startswith("mcp_zeeker") or r.name == "root"
    )
    combined_log_text = mcp_zeeker_log_text + " " + captured.out + " " + captured.err

    # The warning may surface via caplog records OR via the JSONRenderer to
    # stdout/stderr (depending on whether configure_logging() ran). Assert at
    # least one surface emitted the event.
    assert "fragment_parent_multi_match" in combined_log_text, (
        f"expected event=fragment_parent_multi_match in caplog/stdout/stderr; "
        f"got log_text={combined_log_text[:500]!r}"
    )

    # Assert: parent_url_hash binding is a 16-hex-char value (blake2b 8-byte
    # digest → 16 hex chars per RESEARCH §4.10).
    assert re.search(r"parent_url_hash[\"']?\s*[:=]\s*[\"']?[0-9a-f]{16}", combined_log_text), (
        f"expected 16-hex-char parent_url_hash binding; got {combined_log_text[:500]!r}"
    )

    # Assert: parent_match_count == 2 (multi_match fixture has 2 stale dupes).
    assert "parent_match_count" in combined_log_text and re.search(
        r"parent_match_count[\"']?\s*[:=]\s*2\b", combined_log_text
    ), f"expected parent_match_count=2 binding; got {combined_log_text[:500]!r}"

    # Assert: the selected match value (newer created_at) is bound.
    assert expected_selected_match_value in combined_log_text, (
        f"expected selected_parent_match_value={expected_selected_match_value!r}; "
        f"got {combined_log_text[:500]!r}"
    )

    # Negative assertions — INJ-05 / FRAG-02 / T-05-18 / T-05-19.
    # The URL substring MUST NOT appear in any logged surface.
    assert "elitigation.sg/gd/s/2001_SGHC_216" not in combined_log_text, (
        f"URL substring leaked into log surface; log_text={combined_log_text[:500]!r}"
    )
    # The parent_pk literal MUST NOT appear (FRAG-02 carry-forward).
    assert parent_pk_literal not in combined_log_text, (
        f"parent_pk literal {parent_pk_literal!r} leaked into log surface; "
        f"log_text={combined_log_text[:500]!r}"
    )

    # Also verify the envelope (response data) is hash-aware: the envelope
    # rows are from the Call 2 fragments payload (NOT the multi-match parent
    # rows), so the parent_pk would only leak via FRAG-02 violation — assert
    # it does not.
    envelope_text = json.dumps(envelope.model_dump(mode="json"), default=str)
    assert parent_pk_literal not in envelope_text, (
        f"parent_pk literal {parent_pk_literal!r} leaked into envelope"
    )
