# Architecture Research

**Domain:** Remote MCP server proxying a Datasette upstream (Singapore legal data)
**Researched:** 2026-05-13
**Confidence:** HIGH (FastMCP middleware, `custom_route`, and Datasette JSON shape verified against current docs; module decomposition is opinionated but grounded in the PRD's locked stack)

---

## Standard Architecture

### System Overview

```
                              ┌──────────────────────────────┐
   MCP client ── HTTP/POST ──▶│       Starlette / Uvicorn    │   (transport)
   (Claude)        /mcp       │     ASGI app built from      │
                              │     FastMCP.http_app()       │
                              └──────────────┬───────────────┘
                                             │
              ┌──────────────────────────────┼────────────────────────────────┐
              │            ASGI middleware (Starlette layer)                  │
              │  RequestIDMiddleware → ClientIPMiddleware → RateLimitMW        │
              │  → AccessLogMiddleware → ErrorTranslationMW (outermost catch) │
              └──────────────────────────────┬────────────────────────────────┘
                                             │
              ┌──────────────────────────────┼────────────────────────────────┐
              │           FastMCP middleware (protocol layer)                 │
              │  on_call_tool: validate → handler → envelope.wrap →           │
              │                                strip_hidden → label           │
              └──────────────────────────────┬────────────────────────────────┘
                                             │
                              ┌──────────────▼───────────────┐
                              │       Tool handlers          │   tools/
                              │  list_databases, list_tables │
                              │  describe_table, search,     │
                              │  query_table, fetch          │
                              └──────────────┬───────────────┘
                                             │ (pure-Python calls;
                                             │  no HTTP knowledge)
                              ┌──────────────▼───────────────┐
                              │   DatasetteClient (async)    │   upstream/
                              │   httpx.AsyncClient pool     │
                              │   + retry + error map        │
                              └──────────────┬───────────────┘
                                             │ HTTPS
                              ┌──────────────▼───────────────┐
                              │      data.zeeker.sg          │
                              │      (Datasette JSON API)    │
                              └──────────────────────────────┘

   Cross-cutting singletons:
     config.py        — HIDDEN_TABLES, HIDDEN_COLUMNS, URL_COLUMNS, LIGHT_COLUMNS,
                        FRAGMENT_PARENTS, rate-limit constants
     errors.py        — error codes + ToolError dataclass
     schema.py        — Pydantic models for tool inputs/outputs and envelope
     observability.py — structured JSON logger, request-context vars
```

### Component Responsibilities

| Component | Module | Owns | Does NOT own |
|---|---|---|---|
| Transport / ASGI host | `src/mcp_zeeker/app.py` | Starlette app assembly, mount, `/healthz`, ASGI middleware stack | Tool logic, upstream knowledge |
| Server entry / tool registration | `src/mcp_zeeker/server.py` | `FastMCP` instance, `@mcp.tool` registration, FastMCP middleware install | Tool bodies, HTTP details |
| Tool layer | `src/mcp_zeeker/tools/` (one module per tool) | Input validation via Pydantic, *composition* of upstream calls, fragment-join orchestration, choosing light vs. requested columns | Talking HTTP, formatting envelope, denylist enforcement, rate limiting |
| Upstream client | `src/mcp_zeeker/upstream/client.py` | `httpx.AsyncClient` pool, URL construction, retries, 4xx/5xx → `ToolError` translation, response shape normalization | Knowing what an MCP envelope looks like, knowing what's hidden |
| Upstream URL builder | `src/mcp_zeeker/upstream/urls.py` | Datasette path/query construction (`{db}/{table}.json`, `_filter_column=`, `_search=`, `_next=`) | Performing requests |
| Filter compiler | `src/mcp_zeeker/upstream/filters.py` | Tool-side `{column, op, value}` triples → Datasette query params; rejects unsupported ops with `invalid_filter_op` | Knowing hidden columns (gets a denylist passed in) |
| Schema / IO models | `src/mcp_zeeker/schema.py` | Pydantic models: `Filter`, `QueryTableInput`, `Envelope`, `Provenance`, `Pagination` | Business logic |
| Config | `src/mcp_zeeker/config.py` | All denylists, mappings, rate-limit constants, base URL — read once at import | Mutable state |
| Errors | `src/mcp_zeeker/errors.py` | `ErrorCode` enum, `ToolError` exception, mapping helpers | Logging, transport concerns |
| FastMCP middleware: envelope | `src/mcp_zeeker/middleware/envelope.py` | Wraps every successful tool result in `{data, provenance, pagination}`; synthesizes citations when absent | Stripping hidden data |
| FastMCP middleware: hidden-data stripper | `src/mcp_zeeker/middleware/hidden.py` | Removes hidden columns from any row/list response; strips hidden-table hits from `search` results; promotes heavy text into `retrieved_content` key | Rate limiting, provenance |
| FastMCP middleware: injection-label | `src/mcp_zeeker/middleware/label.py` | (Optional) ensures the fixed trailing sentence is appended to tool descriptions at registration time; verifies envelope shape | — |
| ASGI middleware: rate limiter | `src/mcp_zeeker/middleware/ratelimit.py` | Token bucket per IP (burst/sustained/daily); reads `X-Forwarded-For`; returns 429 + `Retry-After` *before* tools run | Token-tier policy (that's config) |
| ASGI middleware: access log | `src/mcp_zeeker/middleware/logging.py` | Request ID, IP-prefix, duration, status; structured JSON | Per-tool business detail (tool reports tool+db+table via contextvar) |
| Observability | `src/mcp_zeeker/observability.py` | Logger factory, contextvar for tool/db/table breadcrumbs | — |
| Healthcheck | `@mcp.custom_route("/healthz", methods=["GET"])` in `server.py` | Liveness only; does not call upstream | Readiness against `data.zeeker.sg` |

---

## Recommended Project Structure

```
src/mcp_zeeker/
├── __init__.py
├── __main__.py                 # python -m mcp_zeeker → uvicorn entry
├── app.py                      # build_app(): Starlette app + ASGI middleware stack
├── server.py                   # FastMCP instance, @tool registrations, custom_route("/healthz")
├── config.py                   # ALL denylists / mappings / limits (single source of truth)
├── schema.py                   # Pydantic: Filter, QueryTableInput, Envelope, Provenance
├── errors.py                   # ErrorCode, ToolError, upstream→tool mapping
├── observability.py            # structured logger + contextvars
├── tools/
│   ├── __init__.py
│   ├── list_databases.py
│   ├── list_tables.py
│   ├── describe_table.py
│   ├── search.py
│   ├── query_table.py          # incl. fragment-join orchestration
│   └── fetch.py
├── upstream/
│   ├── __init__.py
│   ├── client.py               # DatasetteClient: httpx.AsyncClient + retry
│   ├── urls.py                 # URL construction for Datasette endpoints
│   ├── filters.py              # Filter triple → Datasette query param compiler
│   └── responses.py            # Normalize Datasette JSON shape ({rows, next, next_url} → internal)
└── middleware/
    ├── __init__.py
    ├── ratelimit.py            # ASGI: token bucket, 429 before tool dispatch
    ├── logging.py              # ASGI: structured access log
    ├── envelope.py             # FastMCP: wrap result in {data, provenance, pagination}
    ├── hidden.py               # FastMCP: strip hidden cols/tables, promote heavy → retrieved_content
    └── label.py                # FastMCP: registration-time tool description discipline

tests/
├── unit/
│   ├── test_filters.py
│   ├── test_envelope.py
│   ├── test_hidden_enforcement.py
│   ├── test_fragment_join.py
│   ├── test_rate_limit.py
│   ├── test_error_mapping.py
│   └── conftest.py             # FakeDatasetteClient fixture
└── integration/                # live, gated by ZEEKER_LIVE=1
    └── test_live_smoke.py
```

### Structure Rationale

- **`tools/` one module per tool**: each tool is a thin async function; module boundary makes registration order, signature, and docstring (which ends with the fixed safety sentence) trivially auditable in the registry PR review.
- **`upstream/` is HTTP-only, denylist-blind**: the client knows Datasette; it does not know what's hidden. The denylist crosses this boundary as a *function argument* or via the response-time stripper middleware. This lets unit tests substitute a `FakeDatasetteClient` that returns canned `dict` payloads without monkeypatching `httpx`.
- **`middleware/` split between ASGI and FastMCP**: rate limiting and access logging happen on the raw HTTP request (must reject 429 *before* spending tool-execution time and *before* hitting the upstream). Envelope wrapping, hidden-data stripping, and labeling happen at the FastMCP protocol layer where the result object exists and is typed.
- **`config.py` flat and immutable**: matches the PRD's "single source of truth" and the registry-review goal — a reviewer can read one file and see every denylist.
- **`schema.py` separate from `tools/`**: Pydantic models are reused by multiple tools (`Filter` appears in `query_table` and arguably `search`); putting them in tool modules creates circular imports.

---

## Architectural Patterns

### Pattern 1: Two-Tier Middleware (ASGI + FastMCP)

**What:** Rate limiting and access logging live as Starlette/ASGI middleware *outside* FastMCP. Envelope wrapping, hidden-data stripping, and label enforcement live as FastMCP `Middleware` subclasses *inside* FastMCP.

**When to use:** Any time you need both transport-level concerns (must run before MCP protocol parsing, returns raw HTTP responses like 429) and protocol-level concerns (need access to the typed `ToolResult` object).

**Trade-offs:**
- Pro: rate-limited requests never enter FastMCP at all → no wasted CPU, no upstream call risk
- Pro: envelope middleware works on structured results, not JSON strings → no double-serialization
- Con: two middleware mental models in the same repo (minor; clearly bounded)

**Example:**

```python
# app.py — ASGI layer
from starlette.applications import Starlette
from starlette.middleware import Middleware
from .middleware.ratelimit import RateLimitMiddleware
from .middleware.logging import AccessLogMiddleware
from .server import mcp

def build_app() -> Starlette:
    inner = mcp.http_app(path="/mcp")  # returns a Starlette app with lifespan
    app = Starlette(
        lifespan=inner.lifespan,
        middleware=[
            Middleware(AccessLogMiddleware),
            Middleware(RateLimitMiddleware),  # innermost ASGI = closest to handler
        ],
        routes=[Mount("/", app=inner)],
    )
    return app
```

```python
# middleware/envelope.py — FastMCP protocol layer
from fastmcp.server.middleware import Middleware, MiddlewareContext

class EnvelopeMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        result = await call_next(context)
        # tool returned raw {rows, next, db, table}; wrap it
        result.structured_content = wrap_envelope(
            payload=result.structured_content,
            tool=context.message.name,
        )
        return result
```

### Pattern 2: Denylist Enforcement at Both Edges

**What:** Hidden-table / hidden-column enforcement runs in two places:
1. **Request-side, in the tool handler**, by validating user-supplied `database`/`table`/`columns` against `config.HIDDEN_TABLES` / `HIDDEN_COLUMNS` *before* calling upstream. Rejected with `unknown_table` / `unknown_column`.
2. **Response-side, in the `HiddenDataMiddleware`**, by stripping hidden columns from any returned rows and dropping rows that originate from hidden tables (relevant for `search` cross-table results).

**When to use:** Any time the denylist is the security boundary and you cannot trust upstream to honor it. Datasette has no awareness of our hidden lists, so we enforce them ourselves on both sides.

**Trade-offs:**
- Pro: defense in depth — a bug in either edge is caught by the other; the success-metric "zero data-leakage regressions" survives a single missed code path
- Pro: response-side strip handles `search` (which queries upstream by phrase and gets back rows from arbitrary tables we didn't pre-validate)
- Con: O(n) post-processing on every response — negligible given response sizes (preview rows, ≤200 rows)

**Example:**

```python
# tools/query_table.py (request edge)
def _validate(db: str, table: str, columns: list[str] | None) -> None:
    if table in config.HIDDEN_TABLES.get(db, set()):
        raise ToolError(ErrorCode.unknown_table, f"Unknown table: {db}.{table}")
    hidden = config.hidden_columns_for(db, table)
    if columns and (bad := set(columns) & hidden):
        raise ToolError(ErrorCode.unknown_column, f"Unknown columns: {sorted(bad)}")

# middleware/hidden.py (response edge)
class HiddenDataMiddleware(Middleware):
    async def on_call_tool(self, context, call_next):
        result = await call_next(context)
        sc = result.structured_content
        if "data" in sc:
            sc["data"] = strip_hidden_rows(sc["data"], sc["provenance"])
        return result
```

### Pattern 3: Fragment-Join in the Tool Layer, Not the Upstream Client

**What:** When `query_table` is called on a `*_fragments` table with a URL-style filter, the *tool handler* orchestrates a two-step call sequence:
1. `client.fetch_row_by_url(parent_db, parent_table, url_column, url)` → returns parent PK
2. `client.query_table(db, fragment_table, filter={parent_fk: pk}, order_by=...)`

The upstream client knows nothing about fragments.

**When to use:** Whenever a "single tool call" semantically requires multiple upstream requests *and* the relationship is encoded in config (here: `FRAGMENT_PARENTS`), not in upstream schema.

**Trade-offs:**
- Pro: upstream client stays a flat 1:1 of Datasette endpoints — easy to test, easy to retry per-call
- Pro: `FRAGMENT_PARENTS` lives in `config.py` alongside the rest of the denylists — single audit surface
- Pro: the fragment-join can be developed and tested as a pure orchestration unit with a `FakeDatasetteClient` that records call order
- Con: two HTTP round-trips per fragment-table query; acceptable per the PRD latency budget (~600ms combined p50 of 300ms × 2)

**Example:**

```python
# tools/query_table.py
async def query_table(db, table, filters=None, ...):
    fragment_meta = config.FRAGMENT_PARENTS.get(f"{db}.{table}")
    if fragment_meta and (url_filter := _extract_url_filter(filters)):
        parent_pk = await _resolve_parent_pk(db, fragment_meta, url_filter)
        filters = _swap_url_for_fk(filters, fragment_meta["parent_fk"], parent_pk)
        sort = sort or [(fragment_meta["order_by"], "asc")]
    return await client.query_table(db, table, filters=filters, sort=sort, ...)
```

### Pattern 4: ToolError Exception → ASGI/FastMCP Error Translation

**What:** Any tool or upstream-client failure raises a `ToolError(code: ErrorCode, message: str, retry_after: int | None = None)`. A single error-translation seam in `server.py` (or as the outermost FastMCP middleware) converts these into the MCP error JSON shape. ASGI-layer 429s for rate limiting bypass FastMCP entirely (raw HTTP response).

**When to use:** Any time you have a stable error catalog and want to keep tool bodies free of "how is this serialized" logic.

**Trade-offs:**
- Pro: tool bodies stay declarative — `raise ToolError(ErrorCode.unknown_table, ...)`
- Pro: error mapping is one file with one truth table — auditable
- Con: must remember to translate at the seam (one-time wiring concern)

---

## Data Flow

### Request Flow (success path)

```
POST /mcp/  (Claude → mcp.zeeker.sg)
   │
   ▼
[ASGI] AccessLogMiddleware: start timer, generate request_id
   │
   ▼
[ASGI] RateLimitMiddleware: read X-Forwarded-For → bucket key
            └─ exhausted → 429 + Retry-After (returns immediately)
   │
   ▼
[FastMCP] parse JSON-RPC envelope, dispatch tool by name
   │
   ▼
[FastMCP middleware: on_call_tool — outermost first]
   ErrorTranslation → HiddenData(post) → Envelope(post) → Label
   │
   ▼
[tool handler] (e.g. tools/query_table.py)
   1. Pydantic-validate input
   2. REQUEST-EDGE denylist check (hidden table/column → ToolError)
   3. Fragment detection? → resolve parent PK via DatasetteClient
   4. Compile filters via upstream/filters.py
   5. Choose column set (light vs caller-supplied)
   │
   ▼
[upstream/client.py] httpx GET https://data.zeeker.sg/{db}/{table}.json?...
            └─ 5xx → one retry → ToolError(upstream_unavailable)
            └─ 4xx → mapped → ToolError(...)
   │
   ▼
[upstream/responses.py] normalize Datasette JSON → {rows, next_cursor, truncated}
   │
   ▼  (return to handler)
[handler] return raw payload {rows, next_cursor, db, table}
   │
   ▼
[FastMCP middleware on the way back — innermost last]
   Envelope.wrap:  {data, provenance, pagination}  ← provenance attached here
                                                     (incl. retrieved_at = now())
   HiddenData.strip: drop hidden cols from rows; for search, drop hidden-table rows;
                     promote heavy text columns → row.retrieved_content[col]
   ErrorTranslation: pass through (no error)
   │
   ▼
[ASGI] AccessLogMiddleware: emit structured JSON log line
   │
   ▼
HTTP 200 → Claude
```

### Response Flow on Error

```
[tool / client raises ToolError]
   │
   ▼
[FastMCP ErrorTranslation middleware]
   ToolError(code, message, retry_after?)
       → MCP error JSON  {error: {code, message, data: {retry_after_seconds?}}}
   │
   ▼
[ASGI AccessLogMiddleware] log with status=error, code=<ErrorCode>
   │
   ▼
HTTP 200 (MCP error envelope; JSON-RPC convention)
```

### Where each cross-cutting concern lives

| Concern | Lives in | Runs on | Notes |
|---|---|---|---|
| Rate limit | `middleware/ratelimit.py` (ASGI) | Request side, *before* MCP parse | 429 short-circuits; never enters FastMCP |
| Denylist (request-side) | Tool handler | Request side, after Pydantic validation | Raises `unknown_table` / `unknown_column` |
| Denylist (response-side) | `middleware/hidden.py` (FastMCP) | Response side | Catches `search` cross-table hits, defense-in-depth for `query_table` |
| Provenance stamp | `middleware/envelope.py` (FastMCP) | Response side, *after* tool returns | `retrieved_at` is "wrap time" — accurate per-request |
| Citation synthesis | `middleware/envelope.py` | Response side | Looks up table → URL column → builds string if not present in row |
| `retrieved_content` promotion | `middleware/hidden.py` | Response side | Heavy columns (allow-listed via `columns`) get moved out of row top level |
| Tool description label | `middleware/label.py` or `server.py` | Registration time (once) | Verifies every tool's docstring ends with the fixed sentence |
| Fragment join | `tools/query_table.py` | Request side, before main query | Uses `config.FRAGMENT_PARENTS` |
| Error mapping | `upstream/client.py` raises → `errors.py` translates → FastMCP error mw serializes | Both sides | Catalog of 9 codes |
| Structured access log | `middleware/logging.py` (ASGI) + `observability.py` contextvars | Wraps every request | Tool layer writes `tool`/`db`/`table` into contextvar; logger reads on exit |

---

## Build Order (Risk-Reduction Ranked)

The goal of each milestone is: *produce a demonstrable artifact* AND *retire the highest remaining unknown*.

| # | Phase | Demonstrable | Unknowns retired | Why this order |
|---|---|---|---|---|
| **M1** | **Skeleton + `list_databases`** | `curl mcp.zeeker.sg/mcp` → MCP handshake; tool returns 4 databases wrapped in envelope (hardcoded provenance for now) | DNS resolves, TLS works, FastMCP streamable HTTP transport works, `httpx.AsyncClient` reaches `data.zeeker.sg`, Datasette JSON shape matches assumptions, envelope shape lands in client correctly | This is the *correct* MVP. `list_databases` is the smallest tool that exercises every layer end-to-end (transport, upstream client, tool registration, envelope shape). It does **not** depend on filters, fragments, search, or rate limiting. If transport is broken, you find out on day 1. |
| **M2** | **Discovery + denylists** | `list_tables`, `describe_table`; hidden tables 404; `config.HIDDEN_TABLES` and `HIDDEN_COLUMNS` populated and audited | Schema discovery vs Datasette's `/{db}.json` and `/{db}/{table}.json?_shape=...` works; denylist enforcement on request side is correct; light vs full column distinction is meaningful | Builds vocabulary the rest of the tools depend on. Forces the denylist code path to exist (used by M3+M5). |
| **M3** | **`query_table` + `fetch` (non-fragment)** | Structured queries against real tables with filter mapping, pagination, light-vs-full columns | Filter compiler is right (translates 11 ops to Datasette query params); cursor pagination round-trips; per-table light column sets are correct; per-table URL→fetch mapping is correct | Biggest single chunk of "is the upstream actually shaped like we think". Filter compiler is the highest-risk pure-logic module. Fragment tables intentionally deferred. |
| **M4** | **`search`** | Cross-database FTS; hidden-table rows stripped from results | Datasette `/-/search.json` shape; response-side hidden-data stripping (the only tool that *needs* the response-side strip in production, not just defense-in-depth) | Forces the response-side `HiddenDataMiddleware` to exist; reuses envelope from M1. |
| **M5** | **Fragment-join** | `query_table` on `*_fragments` tables with a URL filter transparently resolves parent PK and orders by per-table column | Two-step orchestration; `FRAGMENT_PARENTS` config; latency budget under combined p95 | High-value, contained risk. By M5 the upstream client and tool layer are solid; this is a pure orchestration test. |
| **M6** | **Envelope hardening + injection labels** | Every tool wrapped consistently; citation synthesized for `pdpc.enforcement_decisions`; fixed safety sentence verified at registration time | Envelope is identical across tools; description discipline auditable in CI | Envelope existed since M1 as a stub; this is when it becomes uniform and reviewable. |
| **M7** | **Rate limiter + structured errors + `/healthz` + access logs** | 429 with `Retry-After` triggers correctly; 9 error codes round-trip; `/healthz` returns 200; JSON logs include request_id/IP-prefix | Token-bucket math (burst + sustained + daily); X-Forwarded-For parsing; ASGI middleware sequencing | Pure infra polish; can land late because tools were already functionally complete. Risk: rate-limit math edge cases; mitigate by exhaustive unit tests on the bucket. |
| **M8** | **Full tests + 24h soak** | Coverage report; soak result: p95 < 1.5s, no leaks | Memory under steady load; concurrency at 50; gated live integration tests stable | Validates non-functional requirements. Soak is the only thing that exercises 24h-window rate-limit math + connection-pool reuse. |
| **M9** | **Submission PR** | PR open against `anthropics/claude-for-legal` with `.mcp.json` entry + README | Reviewer feedback | External; not technical risk. |

### Risk-Reduction Ranking (highest unknown first)

1. **Does FastMCP's streamable HTTP transport actually work behind our deployment topology?** — M1 (skeleton + `list_databases`)
2. **Is Datasette's JSON response shape what we think (rows, next_url, columns)?** — M1, validated harder in M3
3. **Does our filter-compiler translate all 11 operators correctly to Datasette query params?** — M3 (`query_table`)
4. **Is the per-table `LIGHT_COLUMNS` set audit-correct for all 26 tables?** — M3, reviewed again in M6
5. **Does the two-step fragment join stay under the latency budget?** — M5
6. **Does the in-memory token bucket behave correctly across burst+sustained+daily windows simultaneously?** — M7, soaked in M8
7. **Will reviewers accept the connector?** — M9 (external)

The PRD's milestone ordering is already correct on this ranking. The only thing this research strengthens is *why* `list_databases` is the MVP: it's not the most interesting tool, but it's the only one that retires four unknowns at once (transport, DNS, upstream reachability, envelope shape) without dragging in filter, search, or fragment complexity.

---

## Middleware Sequencing (Decided)

### ASGI Layer (outside FastMCP)

Order outermost → innermost (each wraps the next):

1. **AccessLogMiddleware** — start timer, generate request_id, emit log on exit (last thing to see the response, first thing to see the request)
2. **ErrorTranslationMiddleware (optional outer catch)** — converts uncaught exceptions to MCP error JSON; in practice FastMCP handles most of this, this is a backstop for ASGI-layer crashes
3. **RateLimitMiddleware** — innermost ASGI; closest to FastMCP. Returns 429 *before* FastMCP parses anything, so an exhausted bucket spends zero CPU on JSON-RPC decoding.

**Rationale for putting RateLimit last (innermost) in the ASGI chain:** Logging and request-ID should still happen for 429s (we want to observe them). If RateLimit were outermost, a 429 wouldn't be logged.

### FastMCP Layer (inside FastMCP, `on_call_tool` hooks)

Order outermost → innermost:

1. **ErrorTranslationMiddleware** — catches `ToolError` raised below, converts to MCP error
2. **EnvelopeMiddleware** — wraps successful tool results in `{data, provenance, pagination}` on the response side
3. **HiddenDataMiddleware** — strips hidden columns / hidden-table rows / promotes heavy text on the response side
4. *(tool handler runs)*

So the unwinding response stack is: handler → HiddenData strip → Envelope wrap → ErrorTranslate (pass-through on success).

**Why HiddenData runs *before* Envelope on the way back (innermost):** Envelope shape includes `provenance` which references `database` + `table`. The hidden-data stripper needs to know which table a row came from to look up `HIDDEN_COLUMNS`. If we wrapped first, the stripper would need to peek into `.provenance`; running it before envelope keeps it operating on the raw handler payload (which already has `db`/`table` keys) and keeps the envelope layer trivial.

**Why hidden-data stripping is *response-side middleware*, not handler responsibility:** The handler can validate the *request* (rejecting hidden inputs) but cannot easily validate the *response* — especially for `search`, which returns rows from arbitrary tables matching a query. Putting the strip in middleware means every tool gets defense-in-depth for free, and the `success_metric` "zero data-leakage regressions" has a single audit point.

**Alternative considered (rejected):** Putting the strip inside the upstream client's response normalizer. Rejected because the upstream client should remain denylist-blind — it's a thin Datasette wrapper. Mixing security policy into the HTTP layer makes it harder to test and review.

---

## Test Seams

Each layer exposes a clean substitution point. Unit tests do not touch the network.

| Seam | What it exposes | How tests use it |
|---|---|---|
| `DatasetteClient` protocol | An abstract async interface: `list_databases()`, `query_table()`, `fetch_row_by_url()`, `search()`. Concrete impl uses `httpx`. | `tests/unit/conftest.py` defines `FakeDatasetteClient` returning canned dicts. Inject into tool handlers via dependency parameter or contextvar. |
| `httpx` transport | `httpx.AsyncClient(transport=httpx.MockTransport(...))` | For testing retry/backoff *inside* `DatasetteClient` without faking the whole client. |
| Filter compiler | Pure function `compile(filters: list[Filter]) → dict[str, str]` | Direct parameterized tests over all 11 operators × edge cases. |
| Envelope wrap | Pure function `wrap_envelope(payload, tool, now=callable)` | Inject `now=lambda: fixed_dt` for deterministic `retrieved_at`. |
| HiddenDataMiddleware | Pure function `strip_hidden(rows, db, table)` underneath, plus middleware wrapper | Test the pure function directly; one integration test exercises the wrapper via FastMCP test client. |
| RateLimiter | Class with `(key, now) → AllowedDecision` | Inject `now=callable` for time control; test burst, sustained, daily independently and combined. |
| FastMCP server | `FastMCP.test_client()` (or in-memory client) | End-to-end tool tests that exercise the full middleware stack with a `FakeDatasetteClient` underneath. |
| ASGI app | `httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app()))` | Tests that need to see 429s, headers, real HTTP semantics — without binding a port. |
| Live integration | Real `DatasetteClient` against `https://data.zeeker.sg` | `pytest.mark.live`, gated by `ZEEKER_LIVE=1` env var; runs in a separate CI job. |

**Wiring the gate:**

```python
# tests/conftest.py
import os, pytest
LIVE = os.getenv("ZEEKER_LIVE") == "1"
pytestmark_live = pytest.mark.skipif(not LIVE, reason="ZEEKER_LIVE=1 to run live")
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = ["live: hits data.zeeker.sg; requires ZEEKER_LIVE=1"]
addopts = "-m 'not live'"  # default: skip live tests
```

CI runs default suite on every PR, runs `-m live` nightly and pre-release.

---

## Alternative Decomposition Considered: Per-Table Tool Definitions

**The alternative:** Instead of six generic tools (`list_databases`, `list_tables`, `describe_table`, `search`, `query_table`, `fetch`), define purpose-built tools per table — e.g. `search_judgments`, `fetch_pdpc_decision`, `list_mom_news`. Some MCP servers in the wild take this shape (one tool per business resource).

**Verdict: REJECTED for this project.** The PRD's six-tool decomposition is correct. Reasons:

1. **Tool-count discipline**: 6 generic tools vs ~26 tool-per-table → 4× larger surface area for review, larger prompt budget consumed by tool definitions in every Claude turn, harder to spec.
2. **URL-as-key contract**: The PRD's invariant is "URL is the universal addressing scheme." Per-table tools would either replicate this contract 26 times (waste) or break it (worse).
3. **Maintenance**: Adding a 27th table to `data.zeeker.sg` should be a config-only change (add to `URL_COLUMNS`, `LIGHT_COLUMNS`, optionally `FRAGMENT_PARENTS`). With per-table tools it would be a code change + tool re-registration.
4. **Consistency for the agent**: A single `query_table(database, table, filters, ...)` is easier for an LLM to use predictably than 26 differently-named tools with subtly different parameter sets.
5. **Registry submission**: The PR to `claude-for-legal` is reviewed for *connector quality*. Six clean tools + one config file is a much smaller, more defensible review surface than 26 tools.

**The one nuance:** the *light column sets* are per-table. So while the *tool surface* is centralized, the *per-table policy* lives in `config.py`. This is the right factoring — tools are the contract; tables are data.

**Module-level implication:** `tools/` has six files, not 26. Each tool reads from `config.py` to specialize behavior per table at runtime.

---

## Scaling Considerations

The PRD locks single-process, in-memory state, and 50 concurrent requests. The architecture is built for that. Future scale paths:

| Scale | Architecture adjustments |
|---|---|
| **v1 (current PRD)** — single process, <50 RPS sustained, anonymous-only | As designed. No changes. |
| **API-key tier** | Swap `RateLimitMiddleware`'s key function from `client_ip` to `api_key_id`; add `AuthMiddleware` in front. No tool changes. |
| **Horizontal scale-out** | Replace in-memory token-bucket store behind `RateLimiter` interface with a Redis-backed implementation. No tool changes. `DatasetteClient` already async, so per-process concurrency stays high. |
| **Hot caching** | Insert a `CachingDatasetteClient` decorator around `DatasetteClient` keyed by URL with short TTLs (out of v1; PRD explicitly forbids mirroring, but rate-limited tier might want it). |

### First Bottleneck Predictions

1. **Upstream latency** (Datasette query under load). Mitigation: connection pool tuning on `httpx.AsyncClient`, per-tool timeouts.
2. **Token-bucket lock contention** under high concurrency in one process. Mitigation: per-IP striped locks rather than a single global lock — only matters above ~200 RPS.
3. **Fragment-join double-RTT** for hot judgments. Mitigation: deferred (would require caching, which is out of scope).

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Putting hidden-data enforcement only at one edge

**What people do:** Validate the request (reject hidden inputs) and trust the response, OR strip the response and trust the request.

**Why it's wrong:** The PRD's success metric is "zero data-leakage regressions." A single edge means a single point of failure. `search` is the proof: it returns rows from tables we didn't pre-validate. Without response-side stripping, a hidden-table row leaks through `search` even if `query_table` is bulletproof.

**Do this instead:** Enforce on both edges. Request side blocks misuse; response side catches what request side can't see (search, future tools).

### Anti-Pattern 2: Mixing envelope-shape logic into tool bodies

**What people do:** Each tool builds its own `{data, provenance, pagination}` envelope by hand.

**Why it's wrong:** Six tools × six envelope-construction sites = six places for the envelope to drift. The PRD has hard guarantees (provenance is *always* attached). Centralizing in middleware gives one audit point.

**Do this instead:** Tools return *raw payloads* (e.g. `{"rows": [...], "next_cursor": "..."}` plus enough context that the envelope middleware knows the `database` and `table`). The middleware wraps.

### Anti-Pattern 3: Letting the upstream client know about denylists

**What people do:** Push the `HIDDEN_COLUMNS` filter into the URL builder ("ask Datasette for everything except `id`").

**Why it's wrong:** Couples HTTP/URL construction to security policy. Datasette can't actually filter columns out anyway — you have to strip server-side. And it makes the upstream client harder to test (it now reads `config.py`).

**Do this instead:** Upstream client is a faithful Datasette wrapper. Denylist policy lives in the middleware (response side) and tool handlers (request side).

### Anti-Pattern 4: Rate-limiting inside FastMCP middleware

**What people do:** Implement rate limit as a FastMCP `Middleware.on_call_tool` hook.

**Why it's wrong:** FastMCP parsing happens before that hook fires. A flooding client still consumes JSON-RPC parsing cost per request. The proper rejection at 429 is an HTTP-layer concern.

**Do this instead:** ASGI Starlette middleware. Reject before MCP parses.

### Anti-Pattern 5: Using the `@custom_route` decorator on a Starlette app that wraps FastMCP

**What people do:** Build the Starlette app first, then try to attach FastMCP `@custom_route` healthchecks to it.

**Why it's wrong:** `@custom_route` registers routes on the FastMCP-owned Starlette app returned by `http_app()`. If you wrap that app in a parent Starlette app, the routes still resolve, but only because they live on the inner mount. There's a known regression (jlowin/fastmcp #556) where mounting under a sub-path breaks `custom_route` resolution.

**Do this instead:** Mount FastMCP at root (`Mount("/", app=mcp.http_app(path="/mcp"))`) and register `/healthz` on the inner app via `@mcp.custom_route("/healthz", methods=["GET"])`. Verify with an integration test that hits `GET /healthz`.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---|---|---|
| `data.zeeker.sg` (Datasette) | `httpx.AsyncClient` JSON GETs; single retry on 5xx; structured error mapping on 4xx | Response shape: `{rows, next, next_url, truncated, ...}`. Use `?_shape=array` or default and normalize. Watch for `_next` cursor pass-through. |
| MCP client (Claude) | Streamable HTTP at `/mcp`; SSE fallback | FastMCP handles transport; we hand it tools + middleware. |

### Internal Boundaries

| Boundary | Communication | Notes |
|---|---|---|
| `tools/*` → `upstream/client.py` | Direct async function call; dependency injection via FastMCP context or module-level singleton initialized at app start | Tools never import `httpx` directly. |
| `tools/*` → `config.py` | Module-level constant reads; never written | Frozen dataclasses or plain dicts. |
| `tools/*` → `errors.py` | `raise ToolError(...)` | Single exception type to bubble up. |
| FastMCP middleware ↔ tool result | `MiddlewareContext` from FastMCP; `result.structured_content` is the mutable handle | Verified via FastMCP docs. |
| ASGI middleware ↔ FastMCP | Plain Starlette ASGI protocol; FastMCP's `http_app()` is just a Starlette app | Lifespan must be propagated when nesting (verified gotcha in FastMCP #510). |

---

## Sources

- [FastMCP Middleware (gofastmcp.com)](https://gofastmcp.com/servers/middleware) — bidirectional `on_call_tool` hook; can modify `result.structured_content`; HIGH confidence
- [Running FastMCP server (gofastmcp.com)](https://gofastmcp.com/deployment/running-server) — streamable HTTP is the recommended transport for production; HIGH confidence
- [FastMCP ASGI / Starlette integration](https://fastmcp.wiki/en/integrations/asgi) — middleware list passed to `http_app()`, mountable at sub-paths; MEDIUM confidence (returned 403 to direct fetch; cross-referenced via search results)
- [FastMCP `custom_route` decorator example](https://gofastmcp.com/servers/server) — `@mcp.custom_route("/health", methods=["GET"])` for liveness; HIGH confidence
- [FastMCP issue #556 — `custom_route` sub-path regression](https://github.com/jlowin/fastmcp/issues/556) — informs Anti-Pattern 5; MEDIUM confidence (issue noted, exact resolution status not verified)
- [FastMCP issue #510 — `http_app()` lifespan gotcha](https://github.com/jlowin/fastmcp/issues/510) — must propagate lifespan when wrapping; HIGH confidence (informs `build_app()` pattern)
- [Starlette Middleware](https://starlette.dev/middleware/) — middleware list ordering (outermost first); HIGH confidence
- [Datasette JSON API](https://docs.datasette.io/en/stable/json_api.html) — response shape (`rows`, `next`, `next_url`, `truncated`); HIGH confidence
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — protocol layer underneath FastMCP; HIGH confidence
- PRD §6, §7, §9, §14, §17 (`/Users/houfu/Projects/zeeker-mcp/prd.md`) — authoritative project constraints

---
*Architecture research for: Remote MCP server proxying Datasette*
*Researched: 2026-05-13*
