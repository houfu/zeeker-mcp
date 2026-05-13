"""
Tests for hidden_columns_for helper (D2-10).

Verifies:
- Global "*" hidden column always present
- Per-table union with global columns
- Tables without per-table entries return global only
"""

from __future__ import annotations

from mcp_zeeker.core.config_lookup import hidden_columns_for


def test_global_hidden_always_present():
    """D2-10: Global 'id' column hidden for all tables regardless of per-table entry."""
    result = hidden_columns_for("any-db", "any-table")
    assert "id" in result


def test_per_table_union():
    """D2-10: Per-table hidden columns union with global columns."""
    result = hidden_columns_for("zeeker-judgements", "judgments_fragments")
    # Must include both the global "id" and the per-table "judgment_id"
    assert {"id", "judgment_id"} <= result


def test_table_not_in_per_table_map():
    """D2-10: Table without per-table entry returns only global hidden columns."""
    result = hidden_columns_for("pdpc", "enforcement_decisions")
    assert result == {"id"}
    assert "judgment_id" not in result
