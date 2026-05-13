"""
Config lookup helpers for denylists and per-table config (D2-10).

Provides hidden_columns_for(database, table) as the SINGLE call-site that reads
config.HIDDEN_COLUMNS. No other module in the codebase may read HIDDEN_COLUMNS
directly — all access must go through this helper (Pitfall 4 prevention).

References: D2-10, Pitfall 4.
"""

from __future__ import annotations

from mcp_zeeker import config


def hidden_columns_for(database: str, table: str) -> set[str]:
    """Return the union of global and per-table hidden columns for database.table.

    config.HIDDEN_COLUMNS shape (Phase 2):
      dict[str, set[str]] keyed on:
      - "*"              — global hidden columns (applied to every table)
      - "<db>.<table>"   — per-table hidden columns

    This is the ONLY call-site for config.HIDDEN_COLUMNS. Never read
    config.HIDDEN_COLUMNS directly from handlers — always use this helper.
    Centralizes the union logic and makes future changes a one-line edit.
    """
    return (
        config.HIDDEN_COLUMNS.get("*", set())
        | config.HIDDEN_COLUMNS.get(f"{database}.{table}", set())
    )
