"""
Pure-unit tests for qhash cursor encode/decode — Phase 3 Wave 0 stub (D3-03).

These tests will REMAIN RED until Plan 03-03 ships `mcp_zeeker.core.cursor`.
Function-body imports (NOT module-level) keep collection successful so pytest
exit-0 with --collect-only works for the whole stub set.

Tests cover:
- Round-trip: decode_cursor(encode_cursor(shape, next), shape) == next
- Shape mismatch raises ToolError(invalid_cursor) — D3-03 anti-replay
- Malformed base64 raises ToolError(invalid_cursor) — defense-in-depth
- Empty Datasette `next` (last page) round-trips
- Canonical shape ordering: filters sorted by (column, op), columns sorted
"""

from __future__ import annotations

import pytest


def test_round_trip():
    """D3-03: encode then decode returns the same datasette_next token."""
    from mcp_zeeker.core.cursor import canonical_shape_str, decode_cursor, encode_cursor

    shape = canonical_shape_str("pdpc", "enforcement_decisions", None, [], None)
    encoded = encode_cursor(shape, "2")
    decoded = decode_cursor(encoded, shape)
    assert decoded == "2"


def test_shape_mismatch_raises_invalid_cursor():
    """D3-03: decode with a different shape rejects the cursor."""
    from fastmcp.exceptions import ToolError
    from mcp_zeeker.core.cursor import canonical_shape_str, decode_cursor, encode_cursor

    shape_a = canonical_shape_str("pdpc", "enforcement_decisions", None, [], None)
    shape_b = canonical_shape_str("pdpc", "enforcement_decisions", "decision_date", [], None)
    encoded = encode_cursor(shape_a, "2")
    with pytest.raises(ToolError, match="invalid_cursor"):
        decode_cursor(encoded, shape_b)


def test_malformed_cursor_raises():
    """D3-03: decode rejects non-base64 / malformed tokens with invalid_cursor."""
    from fastmcp.exceptions import ToolError
    from mcp_zeeker.core.cursor import canonical_shape_str, decode_cursor

    shape = canonical_shape_str("pdpc", "enforcement_decisions", None, [], None)
    with pytest.raises(ToolError, match="invalid_cursor"):
        decode_cursor("!!!not-base64url!!!", shape)


def test_empty_datasette_next_round_trips():
    """D3-03: an empty datasette_next token (last page) round-trips cleanly."""
    from mcp_zeeker.core.cursor import canonical_shape_str, decode_cursor, encode_cursor

    shape = canonical_shape_str("pdpc", "enforcement_decisions", None, [], None)
    encoded = encode_cursor(shape, "")
    decoded = decode_cursor(encoded, shape)
    assert decoded == ""


def test_filters_sorted_canonically():
    """D3-03: filter list order does not affect the canonical shape hash.

    Two compute orderings of the same logical filter set MUST produce the same
    canonical shape string, so a paginated cursor remains valid regardless of
    how the LLM ordered the filter clauses in the follow-up call.
    """
    from mcp_zeeker.core.cursor import canonical_shape_str

    filters_ab = [
        {"column": "title", "op": "exact", "value": "x"},
        {"column": "organisation", "op": "contains", "value": "y"},
    ]
    filters_ba = [
        {"column": "organisation", "op": "contains", "value": "y"},
        {"column": "title", "op": "exact", "value": "x"},
    ]
    shape_ab = canonical_shape_str("pdpc", "enforcement_decisions", None, filters_ab, None)
    shape_ba = canonical_shape_str("pdpc", "enforcement_decisions", None, filters_ba, None)
    assert shape_ab == shape_ba
