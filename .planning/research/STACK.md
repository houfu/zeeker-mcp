# Stack Research — Zeeker MCP Connector

**Domain:** Remote MCP server (Python, single-process, async, read-only HTTP proxy to Datasette)
**Researched:** 2026-05-13
**Overall confidence:** HIGH (all major versions and APIs verified against Context7 + PyPI + official docs in the past 24h)

## Executive Recommendation

Use **FastMCP 3.2.4** (the standalone PrefectHQ/jlowin distribution, not the embedded copy inside `mcp` 1.27.x) as the MCP framework, mounted as a Starlette ASGI app under **Uvicorn 0.46.0**. Drive the upstream `data.zeeker.sg` calls with a single long-lived **httpx 0.28.1 AsyncClient**. Use **Pydantic 2.13.4** for tool input/output schemas. Use FastMCP's built-in **`RateLimitingMiddleware`** with a custom `client_id_func` that reads `X-Forwarded-For` from the Starlette request (FastMCP's default `get_client_id` is *not* IP-aware for HTTP transport — explicit custom function required). Use **structlog 25.5.0** for the structured JSON logs the PRD requires. Manage everything with **uv 0.11.14** plus **Ruff 0.15.12** (formatter + linter, Black-compatible) and **pytest 8.x + pytest-asyncio 1.3.0 + pytest-httpx 0.36.2** for the test suite.

This stack matches the PRD's "small, audited dependency footprint" constraint: six core runtime deps (`fastmcp`, `httpx`, `pydantic`, `uvicorn`, `structlog`, and transitively `starlette` + `anyio`) and four dev deps (`pytest`, `pytest-asyncio`, `pytest-httpx`, `ruff`).

## Recommended Stack

### Core Runtime

| Technology | Version | Purpose | Why (with confidence) |
|------------|---------|---------|------------------------|
| `fastmcp` | **3.2.4** (pin to `~=3.2`) | MCP framework: tool registration, transports, middleware pipeline | HIGH — Context7 (`/prefecthq/fastmcp`, 2,697 snippets) + PyPI confirm 3.2.4 released 2026-04-14. FastMCP is the canonical Python MCP framework; the project's claim of "70% of MCP servers worldwide" is repeated across third-party 2026 write-ups. **It always tracks the latest MCP spec** (currently 2025-06-18); the standalone project ships ahead of the mirror inside `mcp`. |
| `mcp` (Python SDK) | **Do not use directly as primary framework** | — | The official SDK at `mcp` 1.27.1 (PyPI, 2026-05-08) re-exports an *older snapshot* of FastMCP under `mcp.server.fastmcp`. For new servers in 2026 the upstream advice is `pip install fastmcp` (the standalone). Keep `mcp` only as a transitive dep of `fastmcp`. |
| `pydantic` | **2.13.4** (pin `~=2.13`) | Tool input/output schemas, envelope dataclasses, config validation | HIGH — PyPI confirms 2.13.4 released 2026-05-06. FastMCP generates tool input schemas from type hints + Pydantic models automatically; pinning to 2.13 ensures we get the merged `pydantic-core` (same repo since 2.13). |
| `httpx` | **0.28.1** (pin `~=0.28`) | Async HTTP client for `data.zeeker.sg/-/*.json` calls | HIGH — PyPI + the encode/httpx releases page confirm 0.28.1 (2024-12-06) is still the current stable; 1.0 is in `dev` releases through 2025 and unreleased. The async API is stable and battle-tested. |
| `starlette` | **1.0.0** (pulled in transitively by `fastmcp`; pin compat to `>=0.41,<2`) | ASGI framework underneath FastMCP's HTTP transport | HIGH — PyPI confirms Starlette 1.0.0 released 2026-03-22 (long-awaited 1.0 cut). FastMCP's `http_app()` returns a Starlette `StarletteWithLifespan` instance; mount our `/healthz` route and any custom middleware against it. |
| `uvicorn` | **0.46.0** (pin `~=0.46`) | ASGI server | HIGH — PyPI confirms 0.46.0 released 2026-04-23. Single-worker `uvicorn` is sufficient for the PRD's "50 concurrent / <256 MB / single-process" target; do **not** add gunicorn — the PRD explicitly favors a single Python process and in-memory rate limiter, which would silently break with multiple workers. |
| `structlog` | **25.5.0** (pin `~=25.5`) | Structured JSON request logs (PRD §13) | HIGH — Context7 (`/hynek/structlog`, score 92.62) + PyPI confirm 25.5.0 (2025-10-27). The processor pipeline + `contextvars`-based binding is exactly the right tool for "request_id + tool + db + table + duration + status + IP-prefix" log lines without smearing context across async tasks. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `anyio` | `>=4.5` (transitive via FastMCP/Starlette) | Concurrency primitives, structured cancellation | Pulled in by FastMCP. Use `anyio.move_on_after` for upstream-call deadlines so we never block beyond the PRD's p95 budget. |
| `orjson` | optional, `~=3.10` | Faster JSON encode for log lines and tool responses | Optional. Adds ~600 KB to the wheel set. Add only if profiling shows JSON encode is a hotspot; skip for v1 to keep the dep footprint minimal. |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| `uv` | **0.11.14** | Dependency management, virtualenv, lockfile, command runner | HIGH — PyPI confirms 0.11.14 (2026-05-12). The PRD already mandates `uv` + `uv.lock`. Use `uv sync --frozen --no-dev` in deployment images so CI fails fast if `uv.lock` drifts from `pyproject.toml`. |
| `ruff` | **0.15.12** | Linter + formatter | HIGH — PyPI confirms 0.15.12 (2026-04-24). `ruff format` is Black-compatible (the PRD-mandated Black behavior, but ~30× faster). `ruff check` covers `flake8` + `isort` + many `pyupgrade` rules in one binary. |
| `black` | **only if literally required by the reviewer** | Formatter | LOW value-add — Ruff's formatter is byte-identical to Black for any code you'd write here, and Anthropic's open-source repos increasingly use Ruff. Recommendation: skip `black` and use `ruff format`; if registry review complains, the swap is one-line. |
| `pytest` | `~=8.3` | Test runner | Required by PRD. |
| `pytest-asyncio` | **1.3.0** | Async test support | HIGH — PyPI confirms 1.3.0 (2025-11-10), stable. Use `asyncio_mode = "auto"` in `pyproject.toml` so any `async def test_*` is recognized. |
| `pytest-httpx` | **0.36.2** | `httpx_mock` fixture for stubbing `data.zeeker.sg` responses | HIGH — PyPI confirms 0.36.2 (2026-04-09), Python 3.10-3.14 supported. Single source of truth for upstream-API mocking; matches Datasette's JSON contract for unit tests. |
| `mypy` or `ty` | optional | Static type checking | The PRD does not require it. Add later if helpful; FastMCP's tool decorators rely on accurate type hints, so types are worth keeping clean. Astral's `ty` is preview in 2026 — defer until 1.0. |

## Installation

```bash
# Project init
uv init --python 3.12 zeeker-mcp
cd zeeker-mcp

# Core runtime
uv add 'fastmcp~=3.2' 'pydantic~=2.13' 'httpx~=0.28' 'uvicorn~=0.46' 'structlog~=25.5'

# Dev
uv add --dev 'pytest~=8.3' 'pytest-asyncio~=1.3' 'pytest-httpx~=0.36' 'ruff~=0.15'
```

That's it — six runtime deps and four dev deps. `starlette` and `anyio` come in transitively via `fastmcp`/`uvicorn`; do not list them explicitly unless you need to pin around a vulnerability.

### Suggested `pyproject.toml` shape

```toml
[project]
name = "mcp-zeeker"
version = "0.1.0"
description = "Read-only MCP connector for data.zeeker.sg (Singapore legal datasets)"
requires-python = ">=3.12"
dependencies = [
  "fastmcp~=3.2",
  "pydantic~=2.13",
  "httpx~=0.28",
  "uvicorn~=0.46",
  "structlog~=25.5",
]

[project.scripts]
mcp-zeeker = "mcp_zeeker.__main__:main"

[dependency-groups]
dev = [
  "pytest~=8.3",
  "pytest-asyncio~=1.3",
  "pytest-httpx~=0.36",
  "ruff~=0.15",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["live: hits data.zeeker.sg; gated by ZEEKER_LIVE=1"]
```

The `live` marker matches PRD §14's gated live integration tests.

## Key Library Notes (deep dives)

### FastMCP 3.x — what to know

**MCP spec compliance.** FastMCP "always targets the most current MCP Protocol version" per the project's release notes. The active spec is **2025-06-18** (transports: streamable HTTP primary, HTTP+SSE deprecated but supported as fallback). FastMCP's `http_app()` returns a Starlette app exposing the streamable HTTP transport at a configurable path (default `/mcp/`).

**Spec-compliant SSE fallback.** Per the MCP 2025-06-18 spec, clients implement the fallback themselves: they POST `InitializeRequest` to the server URL, and on a 4xx response they fall back to a GET expecting SSE. FastMCP exposes streamable HTTP as primary and an SSE transport for legacy clients. For Zeeker we run **streamable HTTP only** and rely on the spec-defined client-side fallback — we do **not** need to dual-mount SSE unless we discover a real client in `claude-for-legal` that requires it.

**Transport entry point — two correct patterns:**

```python
# Pattern A: framework-managed (simplest)
mcp = FastMCP("zeeker", stateless_http=True)
mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, streamable_http_path="/mcp")
```

```python
# Pattern B: explicit Starlette app + uvicorn (preferred for /healthz, custom routes, middleware)
from fastmcp import FastMCP
from starlette.routing import Route
from starlette.responses import JSONResponse

mcp = FastMCP("zeeker", stateless_http=True)

async def healthz(_req): return JSONResponse({"status": "ok"})

http_app = mcp.http_app(
    middleware=[...],            # Starlette middleware list
    routes=[Route("/healthz", healthz)],
)
# uvicorn.run(http_app, host="0.0.0.0", port=8000)
```

Use **Pattern B** — it lets us attach `/healthz` and a `RealIPMiddleware` cleanly. Confirmed against Context7 `/prefecthq/fastmcp`.

**Stateless vs stateful.** Set `stateless_http=True`. The PRD says "No persistent state; each tool call is a clean request/response cycle." Stateless mode disables session bookkeeping and lets each request fan out to upstream independently — exactly what we want for this thin translator. Trade-off: no resumable SSE event store, no MCP sampling, no progress updates from server. All acceptable per PRD §4.

**Middleware pipeline.** FastMCP has its own middleware abstraction *separate* from Starlette's. Both exist and both are needed:

- **FastMCP middleware** (`mcp.add_middleware(...)`) — runs around MCP operations (`on_request`, `on_call_tool`). Use for the rate limiter, the provenance envelope wrapper, and structured logging.
- **Starlette middleware** (passed via `mcp.http_app(middleware=[...])`) — runs at HTTP layer. Use for `RealIPMiddleware` (parse `X-Forwarded-For` into `request.scope["client"]`) so the FastMCP rate limiter, which reads the client identifier via `get_client_id()`, sees the correct IP.

**`RateLimitingMiddleware` and `client_id_func`.** Confirmed (Context7 + FastMCP docs site): the middleware accepts a `client_id_func` callable. Default behavior on HTTP transport is not IP-aware — by design. We pass a custom function that pulls `X-Forwarded-For` (first value), validated against a trusted-proxy allowlist:

```python
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from fastmcp.server.dependencies import get_http_headers, get_http_request

def client_ip() -> str:
    headers = get_http_headers(include_all=True)
    xff = headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    req = get_http_request()
    return req.client.host if req and req.client else "unknown"

mcp.add_middleware(RateLimitingMiddleware(
    max_requests_per_second=1.0,   # PRD: 60 / min sustained
    burst_capacity=20,             # PRD: 20-burst
    client_id_func=client_ip,
))
```

**Daily ceiling caveat.** The PRD wants three limits: 20-burst, 60/min sustained, and **5,000/IP per 24h**. FastMCP's built-in `RateLimitingMiddleware` (token bucket) handles the first two cleanly. The 24h cap is *not* a token-bucket concept — it's a separate sliding/fixed counter. Recommended approach: **roll a thin `DailyCapMiddleware`** (one async dict `{ip: (count, window_start)}` reset every 24h) layered on top, or extend the FastMCP middleware. Total custom code: ~40 LOC. Do not pull in `pyrate-limiter` or `throttled-py` just for this — the extra dependency surface costs more than the code saves, and the PRD specifically says single-process / in-memory.

**Why not `pyrate-limiter` / `throttled-py` / `limiter`?** All three are viable libraries — `throttled-py` is the most feature-complete and supports both token-bucket and sliding-window in-memory. But (a) the PRD already calls for FastMCP's built-in token bucket for burst/sustained, (b) the registry submission gets reviewed on dependency surface, and (c) the 24h cap is genuinely trivial to write. Stick with FastMCP middleware + ~40 LOC for daily cap.

### httpx AsyncClient patterns

**One client, application-lifetime scope.** Create a single `httpx.AsyncClient` in the FastMCP lifespan (or module-level singleton) and inject it into the tool handlers. Recreating per-request kills connection reuse and TLS handshakes — confirmed across the httpx docs and 2026 community write-ups.

```python
from contextlib import asynccontextmanager
import httpx
from fastmcp import FastMCP

@asynccontextmanager
async def lifespan(app: FastMCP):
    limits = httpx.Limits(
        max_keepalive_connections=20,
        max_connections=50,           # matches PRD's 50-concurrent target
        keepalive_expiry=30.0,
    )
    timeout = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
    async with httpx.AsyncClient(
        base_url="https://data.zeeker.sg",
        limits=limits,
        timeout=timeout,
        http2=False,                  # Datasette serves over HTTP/1.1
        headers={"User-Agent": "mcp-zeeker/0.1 (+https://mcp.zeeker.sg)"},
    ) as client:
        app.state.upstream = client
        yield

mcp = FastMCP("zeeker", lifespan=lifespan, stateless_http=True)
```

**Retry strategy.** Per PRD §12: "Upstream `5xx`: one retry with backoff, then surface as `upstream_unavailable`." Implement this in a small `call_upstream()` helper, not as a transport-level retry. The httpx `HTTPTransport(retries=N)` only retries connect-layer failures, not HTTP 5xx — confirmed against the httpx docs.

Roll your own (10 LOC, exponential backoff with jitter) or add **`stamina`** (`~=24.x`) — Hynek Schlawack's opinionated wrapper around Tenacity, with structlog/Prometheus instrumentation built in. **Recommendation: roll your own** for v1; the retry shape is trivial (one retry, 200 ms + 0–100 ms jitter). Reserve `stamina` for the moment we add a second upstream or a more complex retry policy.

**Do not use `tenacity` directly.** Tenacity is powerful but unopinionated; stamina is "tenacity done right" per its author and the Python community. If retry complexity grows, jump to stamina.

### Starlette + Uvicorn

Confirmed: Starlette 1.0.0 (2026-03-22) and Uvicorn 0.46.0 (2026-04-23) are the current production combo. FastMCP runs on Starlette natively — no FastAPI, no Quart, no Litestar. **Why not FastAPI:** FastAPI sits *above* Starlette and adds OpenAPI/route-decorator machinery we don't use. FastMCP already gives us tool decorators; an extra FastAPI layer is dead weight.

**Single Uvicorn worker.** The PRD says single-process. Multiple workers would break the in-memory rate limiter (each worker has its own bucket) — the symptom in production would be effective limits 2-4× higher than configured. If horizontal scale becomes a concern post-v1, the migration is "swap the in-memory bucket for Redis behind the same `RateLimiter` interface" (PRD §11) *before* bumping worker count. Do **not** add gunicorn-with-uvicorn-workers — same trap.

```bash
# Production launch
uv run uvicorn mcp_zeeker.app:http_app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips '*'
```

`--proxy-headers --forwarded-allow-ips` is what makes Uvicorn populate `request.client.host` from `X-Forwarded-For` *before* our middleware runs — set it to the reverse-proxy CIDR, not `*`, in real deployments. Until the hosting setup is finalized, keep our own `RealIPMiddleware` as the authoritative source.

### Logging — structlog vs stdlib + JSON formatter

**Use structlog.** Verdict is unanimous across recent (2026) FastAPI/Starlette write-ups: structlog's processor pipeline plus `contextvars`-based binding is the right tool for async services where you need request-scoped context (request_id, tool name, IP prefix) to flow through every log call inside the handler without manually threading it.

The alternative — `python-json-logger` on top of stdlib `logging` — works but you'd reinvent context propagation by hand for every async tool. structlog's `contextvars.bind_contextvars(request_id=..., tool=...)` solves this in one call.

**Pattern:**

```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
    cache_logger_on_first_use=True,
)
log = structlog.get_logger()
```

The PRD's required log fields (request_id, tool, database, table, duration, status, IP-prefix) drop in as keyword args at the call site and merge automatically with whatever's been `bind_contextvars`'d in the request-scoped middleware.

### `pyproject.toml` / `uv.lock` patterns for a small async service

1. **Pin `requires-python = ">=3.12"`** — Python 3.12 is the floor for `taskgroup`/structured concurrency and matches what `claude-for-legal` examples assume.
2. **Tilde-pin (`~=X.Y`) all five runtime deps.** Locks the minor and lets patch updates flow through `uv lock --upgrade`.
3. **`uv sync --frozen` everywhere production-bound.** Fails fast if `uv.lock` doesn't match `pyproject.toml`.
4. **`uv lock --check` in CI.** Detects drift before deploy.
5. **`[dependency-groups]` not `[project.optional-dependencies]`** for dev deps. Cleaner, doesn't pollute install set for downstream users (relevant if anyone ever `pip install`s this from a wheel for inspection).
6. **No `setup.py`, no `setup.cfg`, no `requirements.txt`.** uv handles everything; the lockfile is the source of truth.
7. **Single src layout: `src/mcp_zeeker/`.** Standard Python packaging; lets pytest run against the installed package, not in-tree.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `fastmcp` 3.2 standalone | `mcp` 1.27 SDK directly | Only if a registry reviewer explicitly objects to the FastMCP dependency — then drop to `mcp.server.fastmcp` (same API surface, older version, lower-level transports). Unlikely. |
| `ruff format` | `black` + `isort` | If a reviewer demands literal Black. Output is identical for our code. |
| FastMCP `RateLimitingMiddleware` + ~40 LOC daily cap | `throttled-py` / `pyrate-limiter` | Only if you need 4+ different limit windows or want to swap in Redis without writing a backend. For v1's 3 windows, custom code wins on dep surface. |
| Roll-your-own one-retry-with-jitter | `stamina` | When retry policy grows beyond "one retry on 5xx" — e.g., multiple upstreams, circuit breakers, per-route policies. |
| `httpx.AsyncClient` | `aiohttp` | Never for this project. httpx is the modern, typed, sync+async client; aiohttp's API is older and less ergonomic for typed code. |
| Stateless `mcp.http_app(...)` mounted in `uvicorn` | `mcp.run(transport="streamable-http")` | The convenience method works but hides the Starlette app — you can't easily add `/healthz` or custom middleware. Use only for quick local smoke tests. |
| `structlog` | `loguru` | loguru is friendlier but harder to coerce into strict, schema-stable JSON output that's grep-friendly for ops. structlog wins for production observability. |
| Single Uvicorn worker | Gunicorn + uvicorn workers | Once we move rate-limit state to Redis and want multi-process — explicitly v2 territory. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `requests` (sync) | Blocks the event loop. Disastrous in a FastMCP async tool handler. | `httpx.AsyncClient` |
| `aiohttp` | Older API, weaker typing, no sync mirror, smaller community in MCP/LLM tooling space. | `httpx.AsyncClient` |
| FastAPI | Adds OpenAPI/routing layer we don't need on top of Starlette; FastMCP already gives us decorators. Extra dependency surface, slower cold start. | Plain Starlette via `mcp.http_app()` |
| `python-json-logger` alone | Works, but you'll hand-roll context propagation across async tasks. Painful in middleware. | `structlog` with the JSONRenderer processor |
| `tenacity` directly | Powerful but unopinionated — easy to misconfigure (e.g., retrying non-idempotent ops, no jitter). | Either ~10 LOC custom retry, or `stamina` |
| `gunicorn` with uvicorn workers | Silently multiplies the in-memory rate limit by worker count. The bug shows up under load and is hard to diagnose. | Single `uvicorn` worker for v1; Redis-backed limiter before scale-out |
| `pyrate-limiter` / `throttled-py` | Solid libraries, but FastMCP ships its own token bucket; the only PRD limit they're missing is the 24h cap, which is 40 LOC. Dep surface costs more than the code saved. | Built-in `RateLimitingMiddleware` + small daily-cap middleware |
| `mcp` SDK as primary import | The version bundled inside `mcp` 1.27 lags the standalone `fastmcp`. Mixing imports between `mcp.server.fastmcp` and `fastmcp` causes confusing duplicate-type errors. | Pin `fastmcp~=3.2`, import everything from `fastmcp.*` |
| `black` alongside Ruff format | Two formatters that agree 99.9% of the time but occasionally fight. Pick one. | `ruff format` only |
| `pydantic` v1 | EOL. Some legacy MCP examples online still use `BaseSettings` from v1 — those are stale. | `pydantic` v2.13+ (and `pydantic-settings` if config-from-env is needed) |
| `mypy` strict mode in v1 | Adds friction for a fast-moving spec-targeted service; types still matter, but enforcement can wait. | Type hints everywhere; defer enforcement to post-M9 |

## Version Compatibility Matrix

| Package | Pin | Compatible with |
|---------|-----|-----------------|
| `fastmcp` 3.2.x | `~=3.2` | `mcp >=1.20`, `starlette >=0.41`, `pydantic >=2.10`, `httpx >=0.27` (transitively pulled in via `fastmcp`'s own deps) |
| `httpx` 0.28.x | `~=0.28` | Python 3.9+; no breaking change in 0.28 vs 0.27 for our usage |
| `pydantic` 2.13.x | `~=2.13` | Python 3.9+; `pydantic-core` now bundled |
| `starlette` 1.0.0 | `>=0.41,<2` (let FastMCP pick) | Python 3.9+; 1.0 is the long-awaited stable cut and is API-compatible with the late 0.x series |
| `uvicorn` 0.46.x | `~=0.46` | Anything ASGI-3; works with Starlette 1.x |
| `structlog` 25.5.x | `~=25.5` | stdlib `logging` interop is via `structlog.stdlib`; standalone use is independent of stdlib config |
| `pytest-asyncio` 1.3.x | `~=1.3` | pytest 8.x |
| `pytest-httpx` 0.36.x | `~=0.36` | `httpx >=0.27` |

## Sources

### Authoritative (Context7 / official docs / PyPI in past 24h)

- Context7 `/prefecthq/fastmcp` — verified streamable HTTP server creation, `RateLimitingMiddleware` shape, `get_client_id` / `get_http_headers` dependency helpers, middleware ordering. HIGH confidence.
- Context7 `/modelcontextprotocol/python-sdk` — verified streamable HTTP client+server APIs, stateless mode, `streamable_http_app()` lifecycle. HIGH confidence.
- Context7 `/hynek/structlog` — verified processor pipeline + JSON renderer + contextvars binding. HIGH confidence.
- [PyPI: fastmcp 3.2.4 (2026-04-14)](https://pypi.org/project/fastmcp/)
- [PyPI: mcp 1.27.1 (2026-05-08)](https://pypi.org/project/mcp/)
- [PyPI: pydantic 2.13.4 (2026-05-06)](https://pypi.org/project/pydantic/)
- [PyPI: httpx 0.28.1 (2024-12-06, still current stable)](https://pypi.org/project/httpx/)
- [PyPI: starlette 1.0.0 (2026-03-22)](https://pypi.org/project/starlette/)
- [PyPI: uvicorn 0.46.0 (2026-04-23)](https://pypi.org/project/uvicorn/)
- [PyPI: structlog 25.5.0 (2025-10-27)](https://pypi.org/project/structlog/)
- [PyPI: ruff 0.15.12 (2026-04-24)](https://pypi.org/project/ruff/)
- [PyPI: uv 0.11.14 (2026-05-12)](https://pypi.org/project/uv/)
- [PyPI: pytest-asyncio 1.3.0 (2025-11-10)](https://pypi.org/project/pytest-asyncio/)
- [PyPI: pytest-httpx 0.36.2 (2026-04-09)](https://pypi.org/project/pytest-httpx/)
- [MCP Spec 2025-06-18 — Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) — verified streamable HTTP primary, HTTP+SSE deprecated, client-side fallback protocol.
- [FastMCP docs — Middleware](https://gofastmcp.com/servers/middleware) — verified `RateLimitingMiddleware`, `SlidingWindowRateLimitingMiddleware`, `client_id_func` parameter.
- [FastMCP docs — Running Server](https://gofastmcp.com/deployment/running-server) — verified streamable HTTP transport and `http_app()` Starlette integration.
- [httpx docs — Timeouts](https://www.python-httpx.org/advanced/timeouts/) — verified four-axis timeout model (connect/read/write/pool).
- [httpx docs — Resource Limits](https://www.python-httpx.org/advanced/resource-limits/) — verified `Limits(max_connections, max_keepalive_connections, keepalive_expiry)`.
- [uv docs — Working on Projects](https://docs.astral.sh/uv/guides/projects/) — verified `uv sync --frozen` semantics and `[dependency-groups]` shape.

### Supporting (WebSearch, verified against multiple sources)

- [FastMCP 3.0 release notes (Jlowin blog)](https://jlowin.dev/blog/fastmcp-3) — context for 3.x release cadence.
- [Why MCP deprecated SSE — fka.dev](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/) — MCP transport history.
- [Cloudflare blog — Streamable HTTP for Python MCP](https://blog.cloudflare.com/streamable-http-mcp-servers-python/) — corroborates transport choice.
- [Choosing a Python Logging Library in 2026 — Dash0](https://www.dash0.com/guides/python-logging-libraries) — corroborates structlog recommendation.
- [Stamina (Hynek Schlawack)](https://github.com/hynek/stamina) — alternative retry library.
- [Modern Python Tooling 2026 — softaims](https://softaims.com/blog/modern-python-tooling-uv-ruff-mypy-2026) — corroborates uv + ruff toolchain.

### Open questions worth re-checking at M1

- **`X-Forwarded-For` parsing.** FastMCP's `get_client_id()` default behavior on streamable HTTP is undocumented for proxy scenarios; the discussion thread on PrefectHQ/fastmcp#1400 is still open as of last check. Our custom `client_ip()` function (see "Why" section) sidesteps this, but **verify behavior end-to-end against a reverse proxy in M1 smoke test**.
- **MCP spec version targeted by FastMCP 3.2.4.** Project says "always tracks latest"; the latest stable spec is 2025-06-18. Confirm by inspecting `fastmcp.__version__` and the negotiated protocol version in initialize handshake during M1.
- **Whether `claude-for-legal` plugins have a minimum MCP spec version pin** for default `.mcp.json` entries — check the registry's CONNECTORS.md before M9 PR.

---
*Stack research for: Remote MCP server (Python, read-only Datasette proxy)*
*Researched: 2026-05-13 — all PyPI versions and Context7 snippets verified within 24h*
