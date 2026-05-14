# Phase 7: Rate limit + structured errors + healthz + logs - Pattern Map

**Mapped:** 2026-05-15
**Files analyzed:** 12 (5 new, 7 modified)
**Analogs found:** 12 / 12

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/mcp_zeeker/core/middleware/rate_limit.py` | middleware | request-response | `src/mcp_zeeker/core/middleware/origin.py` | exact (ASGI class, reject-or-passthrough shape) |
| `src/mcp_zeeker/core/errors.py` | utility | none | `src/mcp_zeeker/core/visibility.py` (raise_* helpers) | exact (NoReturn raise helpers, ToolError "code: message" pattern) |
| `src/mcp_zeeker/core/middleware/error_enrichment.py` | middleware | request-response | `src/mcp_zeeker/core/middleware/retrieved_at.py` | exact (FastMCP `on_call_tool` wrapper shape) |
| `tests/test_rate_limit.py` | test | none | `tests/test_app.py` (ASGI-layer rejection tests) + `tests/test_datasette_client_retry.py` (time-sensitive assertions) | role-match |
| `tests/test_error_catalog.py` | test | none | `tests/test_filter_compiler.py` (ToolError-shape assertions) | exact |
| `src/mcp_zeeker/app.py` (modified) | config | none | self (lines 97-112 middleware list) | self |
| `src/mcp_zeeker/config.py` (modified) | config | none | self (lines 440-467 TRUSTED_PROXY_DEPTH + LOG_FIELDS block) | self |
| `src/mcp_zeeker/core/datasette_client.py` (modified) | client | request-response | self (lines 126-158 `_request_with_retry`) | self |
| `src/mcp_zeeker/core/filter_compiler.py` (modified) | utility | none | self (lines 115, 129, 134 ToolError raises) | self |
| `tests/conftest.py` (modified) | test | none | self (frozen_retrieved_at fixture at lines 414-434) | self |
| `tests/test_datasette_client_retry.py` (modified) | test | none | self (lines 44-89 502/503/504 patterns) | self |
| `README.md` (modified) | docs | none | n/a | n/a |

---

## Pattern Assignments

### `src/mcp_zeeker/core/middleware/rate_limit.py` (middleware, request-response)

**Analog:** `src/mcp_zeeker/core/middleware/origin.py`

**Imports pattern** (`origin.py` lines 1-8):
```python
from __future__ import annotations

from collections.abc import Sequence

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
```
Rate-limit middleware replaces `JSONResponse` with `Response` (for custom headers) and adds `import json`, `import time`, `import math`, `import structlog`, `from datetime import datetime, timezone, date`, `from dataclasses import dataclass`.

**ASGI class skeleton pattern** (`origin.py` lines 11-32):
```python
class OriginAllowlistMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Sequence[str]) -> None:
        self.app = app
        self.allowed = set(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        origin = headers.get("origin")
        ...
        if origin is not None and origin not in self.allowed:
            response = JSONResponse(
                {"error": "origin_not_allowed"},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
```
Copy this exact ASGI `__call__` shape. Replace the origin-check block with the token-bucket check. Replace `JSONResponse` rejection with a `Response(content=json_body, status_code=429, headers={"Retry-After": str(retry_after)}, media_type="application/json")` rejection.

**Header decode pattern** (`origin.py` line 32):
```python
headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
```
Use exactly this form for decoding raw ASGI scope headers — do not use `HTTPConnection` (not available at ASGI layer without running the full Starlette request parse).

**Synthetic log line pattern** (`access_log.py` lines 36-43):
```python
logger.info(
    "tool_call",
    tool=tool_name,
    duration_ms=duration_ms,
    status=status,
    error_code=error_code,
)
```
The rate-limit middleware emits its own log line using `logger.info("tool_call", tool=None, database=None, table=None, duration_ms=..., status="rejected", error_code="rate_limited")`. The `request_id` and `ip_prefix` fields are automatically picked up from the structlog contextvar (bound by `RequestIdMiddleware` upstream) via the `merge_contextvars` processor — no explicit binding needed.

**Contextvar read pattern** (`request_id.py` lines 26-31):
```python
headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
incoming = headers.get("x-request-id", "")
```
For reading `request_id` in the 429 body, use `structlog.contextvars.get_contextvars().get("request_id", "")` rather than parsing headers — `RequestIdMiddleware` already bound it to the contextvar before `RateLimitMiddleware` runs.

**Divergence from analog:**
- Constructor takes `burst: int`, `sustained_per_second: float`, `daily_limit: int`, `store_cap: int`, `idle_ttl_seconds: float`, `time_provider: Callable[[], float] = time.monotonic` (injected clock for tests — mirrors the `frozen_retrieved_at` injection pattern).
- Maintains `_store: dict[str, BucketState]`, `_last_sweep_ts: float`, `_sweep_interval: float` as instance state.
- Must add `__slots__` to `BucketState` dataclass (28 MB target under 100k cap — see RESEARCH.md Bucket Store section).

---

### `src/mcp_zeeker/core/errors.py` (utility, none)

**Analog:** `src/mcp_zeeker/core/visibility.py` (raise_* helpers)

**Imports pattern** (`visibility.py` lines 19-27):
```python
from __future__ import annotations

from typing import NoReturn

from fastmcp.exceptions import ToolError

from mcp_zeeker import config
from mcp_zeeker.core.config_lookup import hidden_columns_for
from mcp_zeeker.core.datasette_client import DatasetteClient
```
`core/errors.py` only needs `from __future__ import annotations`, `from typing import NoReturn`, and `from fastmcp.exceptions import ToolError`. No config or client imports.

**Core raise-helper pattern** (`visibility.py` lines 34-40 and 87-108):
```python
def raise_unknown_database(database: str) -> NoReturn:
    """Single emission point for unknown_database errors (ERR-02, D2-17)."""
    raise ToolError(f"unknown_database: Database not found: {database}")

def raise_invalid_query() -> NoReturn:
    """INJ-05: the message is a FIXED literal. The user query string is NEVER
    interpolated, f-string'd, or otherwise echoed."""
    raise ToolError("invalid_query: query syntax not supported")
```
All 11 catalog codes follow this exact pattern: `ToolError("code: human readable message")` where the code is the prefix before `: `. For INJ-05-sensitive codes (`invalid_query`, `query_timeout`, `upstream_unavailable`, `rate_limited`), the message MUST be a fixed literal with no `{variable}` substitution.

**Code + message convention** (`filter_compiler.py` lines 115, 129, 134):
```python
raise ToolError(f"unknown_column: Column not found: {f.column}")
raise ToolError("invalid_filter_op: value required for this operator")
raise ToolError("invalid_filter_op: in/notin value must be a flat list of str/int/float")
```
Identifiers (column names, database names, table names) MAY be echoed in error messages. Filter values and query strings MUST NOT be echoed (INJ-05 / T-03-01).

**Phase 7 additions to catalog** (new codes in `core/errors.py`):
```python
def raise_query_timeout() -> NoReturn:
    """Single emission point for query_timeout (ERR-02). Fixed literal — no URL echoed."""
    raise ToolError("query_timeout: Query timed out")

def raise_upstream_unavailable() -> NoReturn:
    """Single emission point for upstream_unavailable (ERR-02). Already raised via
    UpstreamCallFailed in tool handlers; this helper is the canonical string form."""
    raise ToolError("upstream_unavailable: upstream call failed")
```

**Divergence from analog:**
- `core/errors.py` is a NEW file that consolidates only the catalog definitions. The existing raise_* helpers in `core/visibility.py` (unknown_database, unknown_table, unknown_column, unsupported_table_for_fetch, not_found, invalid_query) remain in `visibility.py` — they are not moved. `core/errors.py` only adds the new Phase 7 codes (`query_timeout`, `upstream_unavailable` canonical form) plus a `CATALOG` constant (tuple of all 11 code strings) for the `test_all_11_codes_in_catalog` test.
- `rate_limited` is NOT a ToolError — it is an ASGI-layer 429. It is included in the `CATALOG` tuple constant only.

---

### `src/mcp_zeeker/core/middleware/error_enrichment.py` (middleware, request-response)

**Analog:** `src/mcp_zeeker/core/middleware/retrieved_at.py`

**Imports pattern** (`retrieved_at.py` lines 22-29):
```python
from __future__ import annotations

import contextvars
from datetime import UTC, datetime

import structlog
from fastmcp.server.middleware import Middleware, MiddlewareContext
```
`error_enrichment.py` replaces `contextvars`, `datetime` imports with `from structlog.contextvars import get_contextvars` and `from fastmcp.exceptions import ToolError`.

**FastMCP `on_call_tool` wrapper pattern** (`retrieved_at.py` lines 71-76):
```python
class RetrievedAtMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        token = tool_started_at.set(datetime.now(tz=UTC))
        try:
            return await call_next(context)
        finally:
            tool_started_at.reset(token)
```
`ErrorEnrichmentMiddleware` wraps the same `on_call_tool` hook but uses try/except rather than try/finally — it intercepts exceptions rather than always-running cleanup:
```python
class ErrorEnrichmentMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        try:
            return await call_next(context)
        except ToolError as exc:
            request_id = get_contextvars().get("request_id", "")
            # Append [request_id: ...] to the error message for ERR-03
            raise ToolError(f"{exc.message} [request_id: {request_id}]") from exc
```

**FastMCP middleware logger pattern** (`access_log.py` lines 7-10):
```python
import structlog
from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = structlog.get_logger()
```

**Divergence from analog:**
- Uses `except ToolError` not `finally` — this middleware intercepts errors rather than always running.
- Must re-raise as a new `ToolError` (not the original) so the appended `[request_id: ...]` is in the error message text. The code prefix (`"unknown_database: ..."`) must be preserved as the prefix so catalog code detection still works.

---

### `tests/test_rate_limit.py` (test, none)

**Analog A:** `tests/test_app.py` (ASGI rejection pattern — lines 57-73)

**ASGI rejection test pattern** (`test_app.py` lines 57-73):
```python
async def test_origin_foreign_rejected_403(asgi_client):
    """TRANSPORT-06: Foreign Origin is rejected with 403 and origin_not_allowed body."""
    resp = await asgi_client.post(
        "/mcp/",
        content=b'{"jsonrpc":"2.0","method":"initialize","id":1}',
        headers={
            "content-type": "application/json",
            "origin": "https://evil.example.com",
        },
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "origin_not_allowed"}
```
Rate-limit tests replace the origin check with a burst exhaustion check. The `asgi_client` fixture works for RATE-02 (verifying 429 fires before JSON-RPC parse — the request body can be a raw POST, not a valid JSON-RPC envelope).

**Analog B:** `tests/test_datasette_client_retry.py` (fake-clock injection + direct method test — lines 24-27)

**Direct-client-fixture pattern** (`test_datasette_client_retry.py` lines 24-27):
```python
@pytest.fixture
def client(httpx_mock: pytest_httpx.HTTPXMock) -> DatasetteClient:
    """Return a DatasetteClient backed by a real AsyncClient that pytest-httpx patches."""
    return DatasetteClient(httpx.AsyncClient(base_url=config.UPSTREAM_URL))
```
For rate-limit unit tests, the fixture pattern is `rate_limiter` (instantiates `RateLimitMiddleware` with an injected `fake_clock`) and `bucket_store` (exposes `rate_limiter._store` directly). These fixtures live in `conftest.py` (single-plan-touch rule — Plan 07-01 only).

**Analog C:** `tests/test_retrieved_at_middleware.py` (FastMCP middleware unit test with contextvar inspection — lines 16-47)

**Contextvar assertion pattern** (`test_retrieved_at_middleware.py` lines 27-47):
```python
assert tool_started_at.get(None) is None  # pre-condition

async def call_next(_ctx):
    captured["bound"] = tool_started_at.get(None)
    return "ok"

ctx = types.SimpleNamespace(message=types.SimpleNamespace(name="dummy"))
result = await RetrievedAtMiddleware().on_call_tool(ctx, call_next)
assert result == "ok"
# ... assert on captured["bound"]
assert tool_started_at.get(None) is None  # reset
```
Rate-limit middleware bucket-state tests use the direct-call pattern: call `rate_limiter._check_bucket(ip, now_mono, now_utc)` directly (unit test of the check function, not the ASGI __call__) with a fake clock to avoid time-sensitivity.

**Divergence from analogs:**
- Rate-limit tests need time manipulation via injected `fake_clock: Callable[[], float]` (a list-index counter or `itertools.count` float). No `freezegun` — matches the Phase 6 `frozen_retrieved_at` injection pattern.
- Log-shape tests (`test_429_log_line_shape`) use `structlog.testing.capture_logs` with `processors=[structlog.contextvars.merge_contextvars]` — identical to `test_logging.py:30`.

---

### `tests/test_error_catalog.py` (test, none)

**Analog:** `tests/test_filter_compiler.py`

**ToolError-shape assertion pattern** (`test_filter_compiler.py` lines 18-26, with a representative assertion):
```python
from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from mcp_zeeker.core.filter_compiler import Filter, compile_filters

VISIBLE = {"title", "organisation", "penalty_amount", "decision_type", "score"}
TYPES = {"title": "TEXT", ...}
```
Error-catalog tests import from `mcp_zeeker.core.visibility` (raise helpers) and `mcp_zeeker.core.errors` (new CATALOG constant). Pattern for asserting on error code prefix:
```python
def test_unknown_database_code_prefix():
    with pytest.raises(ToolError) as exc_info:
        raise_unknown_database("test-db")
    assert exc_info.value.message.startswith("unknown_database: ")
```

**INJ-05 canary pattern** (`test_filter_compiler.py` docstring line 15 + hostile input corpus):
The hostile-input corpus in `tests/_corpus/hostile_inputs.py` provides injection canaries. `test_error_catalog.py` should verify that none of the canary strings appear in ToolError messages when used as arguments to raise helpers.

**Log-field-shape assertion pattern** (`test_logging.py` lines 24-49):
```python
bind_request("locked-test", "10.0.0")
try:
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap:
        structlog.get_logger().info("tool_call", tool="list_databases", ...)
finally:
    clear_request()

allowed_keys = set(config.LOG_FIELDS) | {"event", "log_level", "level", "timestamp"}
extra_keys = set(line.keys()) - allowed_keys
assert extra_keys == set(), f"Unexpected keys: {extra_keys!r}"
```
Use this exact `capture_logs` + `allowed_keys` pattern in `test_error_catalog.py` for the `test_429_log_line_shape` test (OBS-03).

---

### `src/mcp_zeeker/app.py` (modified — middleware insertion)

**Analog:** self (lines 97-112)

**Current middleware list** (`app.py` lines 102-110):
```python
middleware=[
    # Outermost first. Request-ID binds the contextvar so subsequent
    # rejects (Origin) carry it in their log line.
    Middleware(RequestIdMiddleware),
    Middleware(
        OriginAllowlistMiddleware,
        allowed_origins=config.ALLOWED_ORIGINS,
    ),
],
```
Insert `RateLimitMiddleware` after `OriginAllowlistMiddleware` and before the implicit `Mount("/mcp", ...)`. The `Middleware()` wrapper takes keyword args matching the constructor: `Middleware(RateLimitMiddleware, burst=config.RATE_BURST, sustained_per_second=config.RATE_SUSTAINED_PER_SECOND, daily_limit=config.RATE_DAILY_LIMIT, store_cap=config.RATE_STORE_CAP, idle_ttl_seconds=config.RATE_IDLE_TTL_SECONDS)`.

**Lifespan hook pattern** (`app.py` lines 39-89 — if rate-limit store needs no async startup, no change needed):
The `RateLimitMiddleware` uses a time-gated synchronous sweep (no background task, per RESEARCH.md recommendation). No lifespan changes required.

---

### `src/mcp_zeeker/config.py` (modified — RATE_* constants)

**Analog:** self (lines 448-467, `TRUSTED_PROXY_DEPTH` + `LOG_FIELDS` block)

**Existing config block pattern** (`config.py` lines 440-467):
```python
# ---------------------------------------------------------------------------
# Transport / security
# ---------------------------------------------------------------------------

# Number of trusted reverse-proxy hops when parsing X-Forwarded-For (Pattern G line 578).
# 1 = one Caddy hop sits in front of the MCP container.
TRUSTED_PROXY_DEPTH: int = 1

# ---------------------------------------------------------------------------
# Observability — OBS-04
# ---------------------------------------------------------------------------

# Locked field set for every structured log line ...
LOG_FIELDS: tuple[str, ...] = (
    "request_id",
    "tool",
    "database",
    "table",
    "duration_ms",
    "status",
    "ip_prefix",
    "error_code",
)
```
Add a new `# Rate limiting — RATE-01..06` section immediately after `TRUSTED_PROXY_DEPTH` and before `# Observability`. Follow the same comment style: section header + inline requirement reference + typed constant. All `RATE_*` constants go in one block so the AST single-source-of-truth test can gate them.

**Constants to add:**
```python
# ---------------------------------------------------------------------------
# Rate limiting — RATE-01..06
# ---------------------------------------------------------------------------

# Token bucket: burst capacity (max tokens in bucket at any time).
RATE_BURST: int = 20
# Token refill rate: sustained 1 request per second = 60 per minute.
RATE_SUSTAINED_PER_SECOND: float = 1.0
# Daily per-IP ceiling: resets at 00:00 UTC (D7-01).
RATE_DAILY_LIMIT: int = 5_000
# Maximum number of IP buckets held in memory (LRU backstop, RATE-04).
RATE_STORE_CAP: int = 100_000
# Idle TTL in seconds for non-daily-locked buckets (D7-03: 15 minutes).
RATE_IDLE_TTL_SECONDS: float = 900.0
```

---

### `src/mcp_zeeker/core/datasette_client.py` (modified — TimeoutException distinction)

**Analog:** self (lines 126-158)

**Existing retry implementation** (`datasette_client.py` lines 126-158):
```python
async def _request_with_retry(self, method: str, url: str, **kw) -> httpx.Response:
    for attempt in (0, 1):
        try:
            resp = await self._http.request(method, url, **kw)
        except httpx.RequestError as exc:
            # D-16: no retry on transport errors in Phase 1
            raise UpstreamCallFailed(str(exc)) from exc
        if resp.status_code in (502, 503) and attempt == 0:
            await asyncio.sleep(0.25 + random.random() * 0.25)
            continue
        if resp.status_code == 504:
            raise UpstreamCallFailed(f"upstream 504 on {url}", status=504)
        if 200 <= resp.status_code < 300:
            return resp
        raise UpstreamCallFailed(
            f"upstream {resp.status_code} on {url}", status=resp.status_code
        )
    raise UpstreamCallFailed(f"upstream retry exhausted on {url}")
```
To distinguish `query_timeout` from generic `upstream_unavailable` (Open Question #3 in RESEARCH.md), add a `httpx.TimeoutException` catch BEFORE `httpx.RequestError` (since `TimeoutException` is a subclass of `RequestError`):
```python
except httpx.TimeoutException as exc:
    raise QueryTimeoutError(str(exc)) from exc
except httpx.RequestError as exc:
    raise UpstreamCallFailed(str(exc)) from exc
```
Add `class QueryTimeoutError(UpstreamCallFailed): pass` in the same module.

---

### `src/mcp_zeeker/core/filter_compiler.py` (modified — INJ-05 verification)

**Analog:** self (lines 115, 129, 134)

**Existing ToolError pattern** (`filter_compiler.py` lines 115, 129, 134):
```python
raise ToolError(f"unknown_column: Column not found: {f.column}")
raise ToolError("invalid_filter_op: value required for this operator")
raise ToolError("invalid_filter_op: in/notin value must be a flat list of str/int/float")
```
Phase 7 verifies these match the locked catalog. No code changes required unless the message prefixes diverge from the canonical form. Verify by inspection that `f.column` is an identifier (not a filter value) and that no `f.value` interpolation exists in any of the ToolError message strings.

---

### `tests/conftest.py` (modified — Phase 7 fixtures)

**Analog:** self (frozen_retrieved_at fixture lines 414-434)

**Existing Phase 6 fixture pattern** (`conftest.py` lines 414-434):
```python
# ---------------------------------------------------------------------------
# Phase 6 — Envelope hardening fixtures (single-plan-touch rule per 02-LEARNINGS)
# ---------------------------------------------------------------------------
# All Phase 6 conftest additions live in Plan 06-01 ONLY. Plans 06-02 / 06-03
# MUST NOT modify this file.

@pytest.fixture
def frozen_retrieved_at():
    """D6-12: Bind tool_started_at to a fixed instant for deterministic snapshots."""
    from datetime import UTC
    from datetime import datetime as _dt
    from mcp_zeeker.core.middleware.retrieved_at import tool_started_at

    frozen = _dt(2026, 1, 1, tzinfo=UTC)
    token = tool_started_at.set(frozen)
    try:
        yield frozen
    finally:
        tool_started_at.reset(token)
```
Add a new `# Phase 7 — Rate limit fixtures (single-plan-touch rule)` section at the bottom of conftest.py. The section comment pattern, docstring style, and function-body import style match the Phase 6 block exactly.

**Phase 7 fixtures to add:**
```python
# ---------------------------------------------------------------------------
# Phase 7 — Rate limit fixtures (single-plan-touch rule per 02-LEARNINGS)
# ---------------------------------------------------------------------------
# All Phase 7 conftest additions live in Plan 07-01 ONLY. Plans 07-02 / 07-03
# MUST NOT modify this file.

@pytest.fixture
def fake_clock():
    """Inject a controllable monotonic clock into RateLimitMiddleware.

    Returns a list [0.0] — tests advance time by setting fake_clock[0] = N.
    The rate limiter constructor takes time_provider=lambda: fake_clock[0].
    Matches the D6-12 'frozen_retrieved_at' injection pattern (no freezegun).
    """
    return [0.0]


@pytest.fixture
def rate_limiter(fake_clock):
    """RateLimitMiddleware instance with injected fake clock and test limits."""
    from mcp_zeeker.core.middleware.rate_limit import RateLimitMiddleware
    from mcp_zeeker import config

    # Dummy ASGI app — the unit tests call _check_bucket directly, not __call__
    async def dummy_app(scope, receive, send):
        pass

    return RateLimitMiddleware(
        dummy_app,
        burst=config.RATE_BURST,
        sustained_per_second=config.RATE_SUSTAINED_PER_SECOND,
        daily_limit=config.RATE_DAILY_LIMIT,
        store_cap=config.RATE_STORE_CAP,
        idle_ttl_seconds=config.RATE_IDLE_TTL_SECONDS,
        time_provider=lambda: fake_clock[0],
    )


@pytest.fixture
def bucket_store(rate_limiter):
    """Direct access to the rate limiter's bucket store for assertion."""
    return rate_limiter._store
```

---

### `tests/test_datasette_client_retry.py` (modified — exhaustion cases)

**Analog:** self (lines 44-89, 502/503 retry-then-succeed pattern)

**Existing retry-and-succeed pattern** (`test_datasette_client_retry.py` lines 44-58):
```python
async def test_502_retries_once_then_succeeds(
    httpx_mock: pytest_httpx.HTTPXMock, client: DatasetteClient
) -> None:
    """502 on first attempt: sleep once, retry, succeed on second attempt."""
    httpx_mock.add_response(status_code=502)
    httpx_mock.add_response(status_code=200, json={"ok": True})

    with patch.object(asyncio, "sleep", new_callable=AsyncMock) as mock_sleep:
        resp = await client._request_with_retry("GET", "/test.json")

    assert resp.status_code == 200
    assert mock_sleep.call_count == 1
    sleep_arg = mock_sleep.call_args[0][0]
    assert 0.25 <= sleep_arg <= 0.50
    assert len(httpx_mock.get_requests()) == 2
```
Phase 7 adds tests for the exhaustion case — replace the second `add_response(200)` with a second `add_response(502)` and assert `UpstreamCallFailed` with `match="retry exhausted"`. Copy the `patch.object(asyncio, "sleep", ...)` wrapper verbatim.

---

## Shared Patterns

### ASGI Header Decode
**Source:** `src/mcp_zeeker/core/middleware/origin.py` line 32
**Apply to:** `rate_limit.py`
```python
headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
```
This is the canonical raw-ASGI header decode form used by every ASGI middleware in this codebase. Use it verbatim in `RateLimitMiddleware.__call__` for XFF extraction.

### ToolError "code: message" Convention
**Source:** `src/mcp_zeeker/core/visibility.py` lines 34-84; `src/mcp_zeeker/core/filter_compiler.py` lines 115, 129, 134
**Apply to:** `core/errors.py`, any new raise sites
```python
raise ToolError("code: Human readable message with no user input echoed")
```
Code is the catalog code string. Colon-space separator. Message is a fixed literal for INJ-05-sensitive codes. Identifiers (database/table/column names) may be f-string interpolated when they are structural identifiers, not user-supplied filter values.

### FastMCP `on_call_tool` Middleware Shape
**Source:** `src/mcp_zeeker/core/middleware/retrieved_at.py` lines 57-76; `src/mcp_zeeker/core/middleware/access_log.py` lines 13-43
**Apply to:** `core/middleware/error_enrichment.py`
```python
class SomeMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        try:
            return await call_next(context)
        finally:
            # cleanup
```
For `ErrorEnrichmentMiddleware`, use `except ToolError` instead of `finally` to intercept and re-raise with enriched message.

### structlog `capture_logs` Test Pattern
**Source:** `tests/test_logging.py` lines 28-49
**Apply to:** `tests/test_rate_limit.py` (OBS-03/04 tests)
```python
bind_request("test-id", "10.0.0")
try:
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap:
        # ... action that emits log
finally:
    clear_request()

allowed_keys = set(config.LOG_FIELDS) | {"event", "log_level", "level", "timestamp"}
extra_keys = set(line.keys()) - allowed_keys
assert extra_keys == set()
```

### conftest Single-Plan-Touch Rule
**Source:** `tests/conftest.py` section headers and docstrings throughout
**Apply to:** Phase 7 conftest additions
All Phase 7 conftest additions land in Plan 07-01 ONLY. Section comment: `# Phase 7 — Rate limit fixtures (single-plan-touch rule per 02-LEARNINGS)`. Plans 07-02+ MUST NOT modify conftest.py.

### pytest-httpx Mock Pattern
**Source:** `tests/test_datasette_client_retry.py` lines 24-89
**Apply to:** `tests/test_datasette_client_retry.py` additions, `tests/test_error_catalog.py`
```python
@pytest.fixture
def client(httpx_mock: pytest_httpx.HTTPXMock) -> DatasetteClient:
    return DatasetteClient(httpx.AsyncClient(base_url=config.UPSTREAM_URL))

async def test_X(httpx_mock, client):
    httpx_mock.add_response(status_code=N)
    httpx_mock.add_response(status_code=M)
    with patch.object(asyncio, "sleep", new_callable=AsyncMock):
        with pytest.raises(UpstreamCallFailed, match="..."):
            await client._request_with_retry("GET", "/test.json")
    assert len(httpx_mock.get_requests()) == 2
```

---

## No Analog Found

All files have analogs in the codebase. The following notes document where the new file legitimately departs from its analog:

| File | Departure from Analog |
|---|---|
| `core/middleware/rate_limit.py` | Stateful (per-IP bucket store) — analogs (`origin.py`, `request_id.py`) are stateless. `__init__` stores `_store: dict`, `_last_sweep_ts`. This is intentional: RATE-06 mandates single-worker, so in-memory state is safe. |
| `core/errors.py` | New standalone module (catalog constant + new raise helpers only). Existing raise helpers stay in `visibility.py` — not migrated. `CATALOG` tuple is the primary new artifact for test assertions. |
| `core/middleware/error_enrichment.py` | Uses `except ToolError` (intercepting) not `finally` (always-running). No contextvar token set/reset — reads the already-bound `request_id` contextvar passively. |

---

## Metadata

**Analog search scope:** `src/mcp_zeeker/` (all modules), `tests/` (all test files)
**Files scanned:** 18 source files + 14 directly relevant test files
**Pattern extraction date:** 2026-05-15

---

## PATTERN MAPPING COMPLETE
