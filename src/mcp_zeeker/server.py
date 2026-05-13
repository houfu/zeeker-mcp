# src/mcp_zeeker/server.py
# Source: 01-PATTERNS.md "src/mcp_zeeker/server.py" section
from __future__ import annotations

from fastmcp import FastMCP

from mcp_zeeker.core.middleware.access_log import StructuredLogMiddleware

mcp = FastMCP(name="zeeker", version="0.1.0")
mcp.add_middleware(StructuredLogMiddleware())

# Tool modules register themselves on import via @mcp.tool decorator.
# These imports MUST run before mcp.http_app() is called.
# Plan 04 overwrites the placeholder tool files with real implementations.
from mcp_zeeker.tools import discovery, retrieval, search  # noqa: F401, E402
