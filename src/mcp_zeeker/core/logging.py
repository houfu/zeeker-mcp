# src/mcp_zeeker/core/logging.py
# Source: 01-RESEARCH.md Pattern J lines 769–811 (paste verbatim, import-path adjusted)
from __future__ import annotations

import structlog

from mcp_zeeker import config  # noqa: F401 — imported for LOG_FIELDS doc reference


def configure_logging() -> None:
    """Configure structlog once at process startup.

    Field set is LOCKED in config.LOG_FIELDS:
      request_id, tool, database, table, duration_ms, status, ip_prefix, error_code
    Plus structlog adds: event, level, timestamp.

    Callers MUST NOT log row contents or user-supplied filter values
    (OBS-04 / INJ-05).
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # pulls request_id etc.
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def bind_request(request_id: str, ip_prefix: str) -> None:
    """Called from RequestIdMiddleware for every request."""
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        ip_prefix=ip_prefix,
    )


def clear_request() -> None:
    structlog.contextvars.clear_contextvars()
