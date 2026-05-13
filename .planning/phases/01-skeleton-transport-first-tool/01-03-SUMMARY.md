---
phase: "01-skeleton-transport-first-tool"
plan: "03"
subsystem: "transport"
tags: [transport, middleware, structlog, origin-allowlist, request-id, fastmcp, starlette, wave-2]
dependency_graph:
  requires:
    - plan-01 (package skeleton, pyproject.toml)
  provides:
    - src/mcp_zeeker/core/ip.py (client_ip, ip_prefix)
    - src/mcp_zeeker/core/logging.py (configure_logging, bind_request, clear_request)
    - src/mcp_zeeker/core/http_client.py (build_http_client)
    - src/mcp_zeeker/core/middleware/origin.py (OriginAllowlistMiddleware)
    - src/mcp_zeeker/core/middleware/request_id.py (RequestIdMiddleware)
    - src/mcp_zeeker/core/middleware/access_log.py (StructuredLogMiddleware)
    - src/mcp_zeeker/server.py (FastMCP mcp instance)
    - src/mcp_zeeker/app.py (Starlette app with nested lifespan)
    - config.py Wave-2 stub (authoritative from plan-02 overwrites on merge)
    - datasette_client.py Wave-2 stub (authoritative from plan-04 overwrites on merge)
    - envelope.py Wave-2 stub (authoritative from plan-02 overwrites on merge)
    - tools/discovery.py, retrieval.py, search.py placeholder stubs
  affects:
    - plan-04 (registers list_databases on the mcp instance from server.py)
    - plan-05 (smoke tests import app from app.py; test middleware in test_app.py, test_logging.py)
tech_stack:
  added: []
  patterns:
    - Pattern A (parent Starlette + nested FastMCP lifespan)
    - Pattern G (XFF client_ip with TRUSTED_PROXY_DEPTH)
    - Pattern H (OriginAllowlistMiddleware — MISSING=ALLOW)
    - Pattern I (StructuredLogMiddleware FastMCP middleware)
    - Pattern J (structlog JSON pipeline with merge_contextvars)
    - Pattern K (RequestIdMiddleware ASGI)
key_files:
  created:
    - src/mcp_zeeker/core/ip.py
    - src/mcp_zeeker/core/logging.py
    - src/mcp_zeeker/core/http_client.py
    - src/mcp_zeeker/core/middleware/origin.py
    - src/mcp_zeeker/core/middleware/request_id.py
    - src/mcp_zeeker/core/middleware/access_log.py
    - src/mcp_zeeker/server.py
    - src/mcp_zeeker/app.py
    - src/mcp_zeeker/config.py (Wave-2 stub)
    - src/mcp_zeeker/core/datasette_client.py (Wave-2 stub)
    - src/mcp_zeeker/core/envelope.py (Wave-2 stub)
    - src/mcp_zeeker/tools/discovery.py (placeholder)
    - src/mcp_zeeker/tools/retrieval.py (placeholder)
    - src/mcp_zeeker/tools/search.py (placeholder)
  modified: []
decisions:
  - "Middleware ordering confirmed: RequestIdMiddleware (outermost ASGI) -> OriginAllowlistMiddleware -> FastMCP StructuredLogMiddleware (on_call_tool)"
  - "configure_logging() called at module top of app.py (before lifespan entry) so structlog is ready for any import-time logger usage"
  - "Nested mcp_app.lifespan(mcp_app) inside parent lifespan is mandatory per Pitfall 1 (missing it causes 500 on first /mcp POST while /healthz returns 200)"
  - "mcp.list_tools() used (not mcp.get_tools()) for envelope-contract guard — verified FastMCP 3.2.4 API"
  - "Envelope-contract guard uses try/except ImportError for Wave-2 tolerance; full assertion active once Plan 02 merges"
  - "Wave-2 stubs created for config.py, datasette_client.py, envelope.py with correct shape so imports resolve before merge"
  - "_DESCRIPTION pattern for tool descriptions: plain string ending with config.TOOL_TRAILER; Plan 04 inherits this convention"
metrics:
  duration: "~15 minutes"
  completed: "2026-05-13T04:00:00Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 14
  files_modified: 0
---

# Phase 01 Plan 03: Transport Stack — Core Utilities, Middleware, Server, App — Summary

**One-liner:** FastMCP + Starlette transport stack with structlog JSON pipeline, Origin-allowlist + request-id ASGI middleware, single-process httpx.AsyncClient factory, and Pattern A nested lifespan composition — importable and lifespan-startable with zero registered tools.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| T1 | Core utilities — ip.py, logging.py, http_client.py | add9409 | config.py (stub), core/ip.py, core/logging.py, core/http_client.py |
| T2 | ASGI + FastMCP middleware — request_id, origin, access_log | 0da071b | core/middleware/origin.py, request_id.py, access_log.py |
| T3 | server.py + app.py — FastMCP instance + Starlette transport | acaa229 | server.py, app.py, datasette_client.py (stub), envelope.py (stub), tools/discovery.py, retrieval.py, search.py (placeholders) |

## Middleware Ordering

**ASGI layer (outermost-first in Starlette middleware list):**
1. `RequestIdMiddleware` — validates/generates `request_id`, binds `request_id` + `ip_prefix` to structlog contextvars, echoes `x-request-id` in response headers.
2. `OriginAllowlistMiddleware` — MISSING Origin = ALLOW; allowlisted Origin = ALLOW; any other Origin = 403 JSON `{"error": "origin_not_allowed"}`. OPTIONS preflight: allowlisted = 204 with CORS headers.

**FastMCP layer (mcp.add_middleware):**
1. `StructuredLogMiddleware` — `on_call_tool` hook; emits one JSON log line per tool call with `tool`, `duration_ms`, `status`, `error_code`; `request_id` and `ip_prefix` propagate automatically via `structlog.contextvars.merge_contextvars`.

**configure_logging() call site:** Module top of `app.py` (line 23, before lifespan definition), so structlog is configured before any logger.info() calls regardless of import order.

## Nested Lifespan Confirmation

The line `async with mcp_app.lifespan(mcp_app):` is present in `app.py` lifespan (verified by grep count = 1). Without this nested call, FastMCP's streamable-HTTP session manager never starts and the first POST to `/mcp` returns 500 while `/healthz` reports healthy (Pitfall 1). The parent lifespan:
1. Enters `build_http_client()` context manager (process-lifetime httpx.AsyncClient)
2. Runs envelope-contract guard (`mcp.list_tools()` — no-op on zero tools in Wave 2)
3. Binds `DatasetteClient` contextvar
4. Enters `mcp_app.lifespan(mcp_app)` (FastMCP session manager)
5. `yield` (serves traffic)
6. `finally` resets DatasetteClient contextvar

## Tool Description Convention for Plan 04

Plan 04 inherits this convention (from Pattern L):
```python
_DESCRIPTION = (
    "List the four Singapore legal databases available on data.zeeker.sg, "
    "with one-line descriptions and visible table counts. Rate limits: "
    "20/burst, 60/minute, 5000/day per IP. "
    f"{config.TOOL_TRAILER}"
)
```
Key requirements (enforced by lifespan-startup guard + Plan 05 contract tests):
- Description MUST end with `config.TOOL_TRAILER` verbatim (INJ-01 / ANNO-02)
- Description MUST mention "rate limit" or the specific limits (ANNO-03)
- Handler return type MUST be `Envelope` (ENV-07)
- Annotations: `readOnlyHint=True, idempotentHint=True, openWorldHint=True` (ANNO-01)

## Wave-2 Stubs — Note for Plan 04

These files are Wave-2 stubs created so imports resolve in the parallel worktree build. **Plan 04 MUST overwrite them with full implementations:**

| Stub File | Minimum Plan 04 Changes |
|-----------|------------------------|
| `src/mcp_zeeker/config.py` | Real env-driven config (Plan 02 provides the authoritative version) |
| `src/mcp_zeeker/core/envelope.py` | Full `Envelope`, `Provenance`, `Pagination` models (Plan 02 provides) |
| `src/mcp_zeeker/core/datasette_client.py` | Full `DatasetteClient` with `get_database()`, `_request_with_retry()`, `UpstreamCallFailed` |
| `src/mcp_zeeker/tools/discovery.py` | `@mcp.tool list_databases` handler using `DatasetteClient.current()` |
| `src/mcp_zeeker/tools/retrieval.py` | Optional stubs with `NotImplementedError` (D-01) |
| `src/mcp_zeeker/tools/search.py` | Optional stub with `NotImplementedError` (D-01) |

## Deviations from Plan

**1. [Rule 1 - Bug] `mcp.get_tools()` does not exist in FastMCP 3.2.4**
- **Found during:** Task 3 verification (lifespan test)
- **Issue:** Plan action specified `await mcp.get_tools()` for the envelope-contract guard. FastMCP 3.2.4 has no `get_tools()` method; the correct API is `await mcp.list_tools()` which returns a list of `FunctionTool` objects.
- **Fix:** Changed to `await mcp.list_tools()` and updated the loop to iterate the list. The contract guard checks `tool.return_type is Envelope` using `FunctionTool.return_type` property (verified correct in FastMCP 3.2.4).
- **Files modified:** src/mcp_zeeker/app.py
- **Commit:** acaa229 (included in Task 3)

**2. [Rule 2 - Missing critical functionality] Wave-2 stubs for config.py, datasette_client.py, envelope.py**
- **Found during:** Task 1 — `from mcp_zeeker import config` would fail without config.py since Plan 01-02 creates the authoritative version in a separate parallel worktree
- **Fix:** Created minimal but correct stubs with the exact D-21 catalog names so all imports resolve. Stubs are clearly labeled with docstrings explaining they are overwritten on merge.
- **Files modified:** src/mcp_zeeker/config.py (new), src/mcp_zeeker/core/datasette_client.py (new), src/mcp_zeeker/core/envelope.py (new)
- **Commit:** add9409, acaa229

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| config.py | src/mcp_zeeker/config.py | Wave-2 parallel worktree stub; Plan 02 provides authoritative version |
| envelope.py | src/mcp_zeeker/core/envelope.py | Wave-2 stub; Plan 02 provides Envelope/Provenance/Pagination models |
| datasette_client.py | src/mcp_zeeker/core/datasette_client.py | Wave-2 stub; Plan 04 provides full implementation |
| discovery.py | src/mcp_zeeker/tools/discovery.py | Placeholder; Plan 04 registers list_databases |
| retrieval.py | src/mcp_zeeker/tools/retrieval.py | Placeholder; Plan 04+ adds stubs |
| search.py | src/mcp_zeeker/tools/search.py | Placeholder; Plan 04+ adds stub |

None of these stubs prevent Plan 03's goal (importable transport stack) — they are by design in the Wave-2 parallel execution model.

## Threat Surface Scan

All T-1-* threats from the plan's threat model are mitigated:
- T-1-OR-01: `OriginAllowlistMiddleware` implements MISSING=ALLOW, allowlisted=ALLOW, else=403
- T-1-LOG-01: `ip_prefix()` truncates IPv4 to /24 and IPv6 to /48; LOG_FIELDS locked in config
- T-1-LIFESPAN-01: `async with mcp_app.lifespan(mcp_app)` is present
- T-1-RID-01: `_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")` bounds client-supplied IDs
- T-1-XFF-01: `client_ip()` reads `TRUSTED_PROXY_DEPTH=1` from config; Caddy overwrite behavior documented
- T-1-PROV-01: lifespan-startup envelope-contract guard is wired (no-op on zero tools; enforces after Plan 04)

No new untrusted network surface introduced beyond what the plan accounts for.

## Self-Check: PASSED

- [x] src/mcp_zeeker/core/ip.py: FOUND
- [x] src/mcp_zeeker/core/logging.py: FOUND
- [x] src/mcp_zeeker/core/http_client.py: FOUND
- [x] src/mcp_zeeker/core/middleware/origin.py: FOUND
- [x] src/mcp_zeeker/core/middleware/request_id.py: FOUND
- [x] src/mcp_zeeker/core/middleware/access_log.py: FOUND
- [x] src/mcp_zeeker/server.py: FOUND
- [x] src/mcp_zeeker/app.py: FOUND
- [x] Commit add9409 (Task 1): FOUND
- [x] Commit 0da071b (Task 2): FOUND
- [x] Commit acaa229 (Task 3): FOUND
- [x] ruff check src/mcp_zeeker/: EXIT 0
- [x] ruff format --check src/mcp_zeeker/: EXIT 0
- [x] import mcp_zeeker.app → routes include /healthz and /mcp: CONFIRMED
- [x] async with app.router.lifespan_context(app): EXIT 0 (no registered tools)
- [x] nested mcp_app.lifespan(mcp_app) line present: CONFIRMED (grep count=1)
