"""
Hostile-input canary corpus for cross-DB search — Wave 0 stub (Plan 04-01).

Mirrors `tests/test_filter_value_safety.py` (Phase 3 / D3-09 / INJ-05) for
the new search handler surface. The 5 canaries are VERBATIM from Phase 3
for parity — D3-09 minimum-viable corpus carried forward into Phase 4.

The query string is the protected threat surface (D4-07 / INJ-05): it must
NEVER appear in any of:
  - the ToolError message (raise_invalid_query is a fixed literal)
  - captured stdout / stderr
  - the structlog log stream (caplog at DEBUG)

Wave 0 RED stub: imports `from mcp_zeeker.tools.search import search` INSIDE
the test function body (NOT at module level) so collection succeeds before
Plan 04-02 ships the handler body. Until Plan 04-02 turns this GREEN, the
test body raises NotImplementedError via the existing stub handler — pytest
records each parametrized case as a failure (RED), but collection stays
clean.

5 canaries (D3-09 / D4-07 minimum-viable corpus):
1. </system>                              — HTML/system-tag injection sentinel
2. NEAR('data' 'protection') AND NOT       — FTS5-operator string
3. "x" * 5001                              — 5 KB oversized payload
4. ZEEKER_CANARY_42                        — plain round-trip detector
5. "\udc80"                                — lone surrogate (UTF-8 boundary)

Plan 04-02 wires the assertion: every canary call to search(...) raises
ToolError (most likely `invalid_query` for NEAR/empty/whitespace inputs or
`upstream_unavailable` for the all-fail path); the canary value never leaks
to stdout/stderr/caplog/ToolError text.
"""

from __future__ import annotations

import pytest

# D4-07 / D3-09 minimum-viable corpus. Order matches the docstring header for
# traceability. Carried forward VERBATIM from Phase 3 tests/test_filter_value_safety.py.
CANARY_STRINGS: list[str] = [
    "</system>",  # HTML/system tag injection sentinel
    "NEAR('data' 'protection') AND NOT",  # FTS5 operators (would error if forwarded raw)
    "x" * 5001,  # 5 KB oversized string
    "ZEEKER_CANARY_42",  # plain round-trip detector
    "\udc80",  # lone surrogate — UTF-8 boundary handling
]


def _surfaces_contain(
    canary: str, *, captured_out: str, captured_err: str, log_text: str, error_text: str
) -> list[str]:
    """Return list of surface names where the canary appears.

    For the lone-surrogate canary, also check `repr()` so backslash-escape
    leakage (e.g. '\\udc80') is detected. Mirrors the
    tests/test_filter_value_safety.py helper.
    """
    leaks: list[str] = []
    for surface_name, surface_text in (
        ("stdout", captured_out),
        ("stderr", captured_err),
        ("log", log_text),
        ("error", error_text),
    ):
        if canary in surface_text:
            leaks.append(surface_name)
        if repr(canary).strip("'\"") in surface_text and repr(canary) != repr(""):
            leaks.append(f"{surface_name}_repr")
    return leaks


@pytest.mark.parametrize("canary", CANARY_STRINGS)
async def test_query_never_echoed(canary: str) -> None:
    """D4-07 / INJ-05: hostile query strings never leak to any output.

    RED until Plan 04-02 ships `mcp_zeeker.tools.search.search`. Wave 0 stub:
    pytest.skip BEFORE any fixture is consumed so pytest-httpx teardown
    doesn't fail on unused stub responses.

    When Plan 04-02 turns this GREEN:
      - Add `bound_datasette_client`, `bound_metadata_cache`, `caplog`,
        `capsys` fixtures to the signature.
      - Remove the `pytest.skip` line.
      - Stub the 4 upstream /{db}.json responses (auto-discovery shape) and
        per-table /{db}/{table}.json?_search=... responses.
      - Call `await search(query=canary, databases=["zeeker-judgements"],
        limit=1)`; catch `ToolError`; capture stdout/stderr/log.
      - Assert `_surfaces_contain(canary, ...)` returns an empty list
        (no surface contains the canary value).

    The `_surfaces_contain` helper above is the contract surface — it stays
    visible in Plan 04-01 so Plan 04-02 has zero re-derivation cost.
    """
    pytest.skip("RED until Plan 04-02 ships the search handler body")
    # Plan 04-02 fills the body. Reference imports kept here so Plan 04-02
    # has a paste-template:
    from fastmcp.exceptions import ToolError  # noqa: F401

    from mcp_zeeker.tools.search import search  # noqa: F401
