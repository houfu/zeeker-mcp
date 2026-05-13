"""
Phase 1 — draft input models for retrieval tools.

Phase 3 (retrieval) will revise per D-04 caveat. These are placeholder
drafts; the filter/sort/cursor/columns types are deliberately loose until
Phase 3's filter compiler defines the narrower shapes.

These models are INTERNAL validators (ANNO-04: extra='forbid').
They are NOT registered as FastMCP tool parameters — tool signatures use
plain Annotated[T, Field(...)] per-parameter style (Pattern E / TRANSPORT-04).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class QueryTableInput(BaseModel):
    """Input model for query_table (Phase 3 will register). PRD §7.4.

    Phase 3 will narrow filters to a Filter model; shape is loose for Phase 1.
    """

    model_config = ConfigDict(extra="forbid")

    database: str
    table: str
    filters: list[dict] | None = None  # Phase 3 narrows to Filter model
    sort: str | None = None
    limit: int = Field(default=50, ge=1, le=200)  # QUERY-07
    cursor: str | None = None
    columns: list[str] | None = None


class FetchInput(BaseModel):
    """Input model for fetch (Phase 3 will register). PRD §7.5."""

    model_config = ConfigDict(extra="forbid")

    database: str
    table: str
    url: str
