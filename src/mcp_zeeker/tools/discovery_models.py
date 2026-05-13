"""
Phase 1 — draft input models for discovery tools.

Phase 3 (retrieval) / Phase 4 (search) will revise per D-04 caveat.

These models are INTERNAL validators (ANNO-04: extra='forbid').
They are NOT registered as FastMCP tool parameters — tool signatures use
plain Annotated[T, Field(...)] per-parameter style (Pattern E / TRANSPORT-04).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ListDatabasesInput(BaseModel):
    """Input model for list_databases. No parameters (PRD §7.1)."""

    model_config = ConfigDict(extra="forbid")


class ListTablesInput(BaseModel):
    """Input model for list_tables (Phase 2 will register). PRD §7.2."""

    model_config = ConfigDict(extra="forbid")

    database: str


class DescribeTableInput(BaseModel):
    """Input model for describe_table (Phase 2 will register). PRD §7.3."""

    model_config = ConfigDict(extra="forbid")

    database: str
    table: str
