"""
Phase 1 — draft input model for search tool.

Phase 4 (cross-database search) will revise per D-04 caveat.

This model is an INTERNAL validator (ANNO-04: extra='forbid').
It is NOT registered as a FastMCP tool parameter — tool signatures use
plain Annotated[T, Field(...)] per-parameter style (Pattern E / TRANSPORT-04).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchInput(BaseModel):
    """Input model for search (Phase 4 will register). PRD §7.6."""

    model_config = ConfigDict(extra="forbid")

    query: str
    databases: list[str] | None = None
    limit: int = Field(default=20, ge=1, le=100)  # SEARCH-05
