"""
DatasetteClient stub for Plan 01-03 (Wave 2 worktree).

NOTE: This is a MINIMAL stub so app.py's lifespan can import and call
DatasetteClient.bind() / DatasetteClient.reset() without error.
Plan 04 overwrites this file with the full implementation (typed methods,
retry-once-with-jitter per D-16, UpstreamCallFailed, DatabaseSummary, etc.).
"""

from __future__ import annotations

import contextvars
from typing import Any

_current: contextvars.ContextVar[Any] = contextvars.ContextVar("datasette_client", default=None)


class DatasetteClient:
    """Minimal stub — Plan 04 provides the real implementation."""

    def __init__(self, http: Any) -> None:
        self._http = http

    @classmethod
    def current(cls) -> DatasetteClient:
        client = _current.get()
        if client is None:
            raise RuntimeError("DatasetteClient.current() called outside a bound scope")
        return client

    @classmethod
    def bind(cls, client: DatasetteClient) -> contextvars.Token:
        return _current.set(client)

    @classmethod
    def reset(cls, token: contextvars.Token) -> None:
        _current.reset(token)
