"""
Envelope stub for Plan 01-03 (Wave 2 worktree).

NOTE: This is a MINIMAL stub so app.py's lifespan can import Envelope
without error. Plan 01-02 (running in parallel) provides the AUTHORITATIVE
implementation. When both worktrees are merged, the 01-02 version overwrites
this one.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Envelope(BaseModel):
    """Minimal stub — Plan 01-02 provides the full implementation."""

    model_config = ConfigDict(extra="forbid")
    data: list[dict]
    provenance: dict
    pagination: dict | None = None
