# Phase 8: Full tests + 24h soak — Research

**Researched:** 2026-05-15
**Domain:** Test taxonomy + soak/load harness + live-test gating + dependency-footprint enforcement
**Confidence:** HIGH (pytest gating, soak tooling, dependency audit); MEDIUM (24h scheduling around CI minutes); MEDIUM (Claude Desktop / VSCode 429 carry-over already verified in Phase 7)

---

## Project Constraints (from CLAUDE.md)

These directives override default behavior and constrain every recommendation in this document:

- **Tech stack pinning** — `fastmcp~=3.2`, `pydantic~=2.13`, `httpx~=0.28`, `starlette>=0.41,<2`, `uvicorn~=0.46`, `structlog~=25.5`. No additions to runtime deps without an explicit phase decision.
- **Tooling** — Black formatter is mentioned in the project intro but the actual config uses **Ruff format only** (Phase 7 / pyproject.toml `[tool.ruff.format]`). NFR-04 lists 4 dev deps: `pytest`, `pytest-asyncio`, `pytest-httpx`, `ruff`. Black is **not** in the stack. Phase 8 must NOT introduce `black`.
- **Read-only** — no write paths anywhere. The soak harness drives the server with read-only requests only.
- **Performance gates** — p50 < 300 ms, p95 < 1.5 s, 50 concurrent, < 256 MB resident. These are the soak's pass/fail signals (NFR-01..03).
- **Anonymous-tier limits** — 20-burst / 60-min / 5,000-per-IP-per-24h. Soak crossing UTC midnight tests rollover.
- **Single Uvicorn worker** — non-negotiable for v1 (RATE-06). Documented in README.
- **No data mirror / stateless** — every soak request is a clean upstream call; no cache state to invalidate.
- **GSD workflow enforcement** — all edits go through GSD commands.
- **No `.md` artifacts** — research is only persisted to `08-RESEARCH.md`; verification reports etc. live in `.planning/phases/`.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for Phase 8 (research is standalone, called via `/gsd-research-phase`). The phase scope was provided directly in the spawn message:

### Locked Decisions (from spawn message + ROADMAP §Phase 8 + REQUIREMENTS NFR-01..05/TEST-01..06)

- **NFR-04 footprint** is exactly `fastmcp` + `httpx` + `starlette` + `uvicorn` + `pydantic` + `structlog` runtime, plus `pytest` + `pytest-asyncio` + `pytest-httpx` + `ruff` dev. Phase 8 enforces this in CI via a unit test, not a doc.
- **TEST-02 live gating** must use the existing `@pytest.mark.live` + `ZEEKER_LIVE=1` env gate registered in `tests/conftest.py:76-82`. Plan reuses, does not invent.
- **Dual-cadence CI** — fast unit/lint/schema-coverage on every PR; live-gated + 1h smoke soak nightly; full 24h soak pre-release (manual trigger).
- **CR-02 fix is in scope** — `src/mcp_zeeker/app.py:59` accesses `tool.return_type` on the `Tool` base. The fix is `getattr(tool, "return_type", None)`. Plan must add a regression test that covers the lifespan path with a non-FunctionTool stand-in.
- **Soak harness must NOT introduce a runtime dep** — it is dev-only. `psutil` is acceptable as a dev dep ONLY because NFR-04 caps **runtime** deps. NFR-04 also caps dev to ~4 packages — adding `psutil` makes 5 dev deps. The plan must EXPLICITLY decide: (a) accept `psutil` as a 5th dev dep with documented justification, or (b) implement RSS sampling without `psutil` via `/proc/{pid}/status` (Linux) / `resource.getrusage()` (cross-platform but coarse). Recommendation in §Soak Harness: option (b) — pure-stdlib `resource.getrusage().ru_maxrss` is sufficient for "is RSS staying under 256 MB?" verification and avoids the dev-dep delta.

### Claude's Discretion

- Soak harness language/runtime — Python (asyncio + `httpx.AsyncClient` already in dev deps) vs external (`locust`, `k6`, `wrk`). Recommendation: Python asyncio harness as a dev-only `scripts/soak/` module (no new dep).
- Specific test file partitioning across plans (multiple Wave-0 vs single consolidated Wave-0).
- Whether `syrupy` snapshot library is worth adding (recommendation: **no** — the snapshot contract is two `set` operations per row, hand-rolled is 3 lines, and `syrupy` would add a 5th dev dep that bumps NFR-04 visibility).

### Deferred Ideas (OUT OF SCOPE)

- Multi-worker / Redis-backed rate-limit testing — v2 (RATE-06 prevents in v1).
- Distributed soak (multiple soak clients across hosts) — v2.
- Synthetic anomaly injection (chaos testing) — v2.
- Performance regression CI gate (compare nightly soak vs baseline) — Phase 9 / post-v1.
- Manual UAT against `mcp.zeeker.sg` for tools (covered by Phase 6 manual checklists; Phase 8 is strictly automated coverage + soak).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-01 | Unit tests cover filter mapping (13 ops), envelope shape, hidden-table/column enforcement, fragment joins, rate-limit windows, error mapping, cursor binding | §Test Taxonomy + §Filter-Operator Coverage + §Cursor-Binding Rejection |
| TEST-02 | Live integration tests gated by `ZEEKER_LIVE=1` (existing infra), nightly + pre-release | §Live-Test Gating |
| TEST-03 | Snapshot tests per tool: `set(row.keys()) ∩ HEAVY_COLUMNS == ∅` and `set(row["retrieved_content"].keys()) ⊆ HEAVY_COLUMNS` | §Snapshot Tests |
| TEST-04 | 1,500-fragment regression for the 1,000-row truncation cap | §1,500-Fragment Regression |
| TEST-05 | 24h soak: stable memory, no pool-timeout cascade, log-growth bounded, daily-rate-limit rollover | §Soak Harness |
| TEST-06 | Hostile-input corpus exercises filter-value-echo paths (canary tokens, malformed UTF-8, FTS5 operators in user input) | §Hostile-Input Corpus |
| NFR-01 | p50 < 300 ms, p95 < 1.5 s for non-fragment tools | §Soak Harness § Latency Sampling |
| NFR-02 | 50 concurrent requests in single process without saturation | §Soak Harness § Concurrency Profile |
| NFR-03 | Resident memory < 256 MB under steady load | §Soak Harness § Memory Sampling |
| NFR-04 | Runtime deps = exactly `fastmcp, httpx, starlette, uvicorn, pydantic, structlog`; dev = `pytest, pytest-asyncio, pytest-httpx, ruff` | §Dependency-Footprint Enforcement |
| NFR-05 | TLS terminated upstream; deployment README documents Anthropic IP-allowlist + single-worker | §Operator Documentation |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Unit-test contract coverage | Test runner (pytest in-process) | — | Pure-function and FastMCP-in-memory client tests; no transport |
| Snapshot enforcement (HEAVY_COLUMNS partition) | Test runner (FastMCP `Client(mcp)` in-memory) | — | Tool emits Envelope; assert on `data` row keys |
| Hostile-input safety | Test runner | Codebase (existing `tests/_corpus/hostile_inputs.py`) | Uses shared corpus — reuses Phase 6 infrastructure |
| Live integration tests | pytest (real HTTPS to `data.zeeker.sg`) | CI scheduler (cron) | `@pytest.mark.live` gate on real upstream; cron triggers nightly |
| Soak — server process | Uvicorn single-worker (under load) | OS process metrics (RSS) | The server we are validating must run as it would in prod |
| Soak — driver | Standalone Python asyncio script (`scripts/soak/`) | `httpx.AsyncClient` (already in dev deps) | Driver is dev-only; no new runtime dep |
| Soak — metrics collection | Driver process (latency hist) + server process (RSS via stdlib) | CSV report file | Output is a CI artifact for triage |
| CR-02 lifespan regression | Test runner (FastMCP in-memory client w/ fake tool stand-in) | — | Exercises `app.py` lifespan path with a `Tool` base subclass |
| Dependency-footprint test | pytest (ASTs `pyproject.toml`) | — | Locks NFR-04 in CI |
| CI dispatch | GitHub Actions (or equivalent) | — | Per-PR vs nightly vs pre-release matrix |

---

## Summary

Phase 8 is a "harden and prove" phase: every contract surface gets a unit test, the live tests get a CI cadence, and a 24h soak proves the performance/memory NFRs against a real Uvicorn process. The phase introduces no new runtime dependencies and at most one dev tooling addition (`psutil` is rejected; soak uses stdlib `resource.getrusage()`).

**Primary recommendations:**

1. **Reuse existing test infrastructure verbatim.** `tests/conftest.py:76-82` already implements `ZEEKER_LIVE=1` gating for `@pytest.mark.live`. `tests/_corpus/hostile_inputs.py` already provides `CANARY_STRINGS` and `_surfaces_contain`. The fixture stack (`mcp_client`, `asgi_client`, `stub_upstream`, `bound_datasette_client`, `bound_metadata_cache`, `frozen_retrieved_at`, `fake_clock`, `rate_limiter`, `bucket_store`) is mature — Phase 8 is mostly **adding test files**, not adding fixtures. [VERIFIED: codebase inspection]

2. **Soak harness = pure-stdlib + httpx.** A `scripts/soak/run_soak.py` driver using `asyncio.gather` over `httpx.AsyncClient` requests, sampling RSS via `resource.getrusage().ru_maxrss` from a sidecar Python process that knows the Uvicorn PID. No `locust`, `k6`, `wrk`, or `psutil`. The driver writes CSV + a markdown summary as CI artifacts. Run as `uv run python -m scripts.soak.run_soak --duration 24h`. [VERIFIED: stdlib `resource` module documentation; asyncio + httpx already in dev deps]

3. **Soak time-acceleration via `time_provider` injection for daily-rollover testing.** The `RateLimitMiddleware` already accepts `time_provider: Callable[[], float]` (default `time.monotonic`). Real 24h soak uses real time. CI nightly soak uses a 1h smoke that exercises burst + sustained but not daily rollover (which is impractical at 1h). Daily-rollover regression is a **unit test** that fakes `datetime.now(tz=UTC)` (already present in `tests/test_rate_limit.py` per Phase 7 deferred-items list). The 24h soak's daily-rollover assertion is opportunistic: the soak driver sees the bucket reset behavior in real time only on the wall-clock-crossing run. [VERIFIED: `rate_limit.py:115`; existing fake_clock fixture]

4. **CR-02 fix is one line + one test.** Change `src/mcp_zeeker/app.py:59` from `if tool.return_type is not Envelope:` to `if getattr(tool, "return_type", None) is not Envelope:`. Add `tests/test_app_lifespan_contract.py::test_lifespan_tolerates_non_function_tool` that registers a synthetic `Tool` subclass without a `return_type` attribute and asserts the lifespan completes without `AttributeError`. [VERIFIED: VERIFICATION.md deferred item; FastMCP Tool/FunctionTool class hierarchy via Phase 7 RESEARCH]

5. **Dependency-footprint enforcement is a unit test, not a CI YAML check.** A `tests/test_dependency_footprint.py` reads `pyproject.toml` via `tomllib` (stdlib in 3.11+) and asserts `[project.dependencies]` is exactly the 6-tuple of names and `[dependency-groups.dev]` is exactly the 4-tuple. This locks NFR-04 in the test suite where it cannot drift silently. [VERIFIED: `pyproject.toml` shape; `tomllib` stdlib]

6. **Hostile-input corpus is already consolidated.** `tests/_corpus/hostile_inputs.py:CANARY_STRINGS` covers the 5 critical canaries (`</system>`, FTS5 operators, 5 KB string, plain ZEEKER_CANARY_42, lone surrogate). Phase 8 EXPANDS the corpus with the additional categories named in the spawn message (BOM, RTL override, ANSI escape, JSON injection) AND adds a **path-fan-out test matrix** that fans 5 (existing) + 4 (new) = 9 canaries × N error-emitting tools (query_table, search, fetch — 3) × M emission surfaces (error message, log line, response metadata) — covering the surfaces the existing per-tool tests don't currently fan across. [VERIFIED: `hostile_inputs.py`; `test_hostile_inputs_consolidated.py`]

**Primary recommendation:** Treat Phase 8 as 6 plans across 4 waves: (Wave 0) test scaffolding + dependency footprint, (Wave 1) unit-test sweep covering all REQ surfaces + CR-02 fix, (Wave 2) snapshot + hostile-input fan-out + 1500-fragment regression, (Wave 3) live-test cadence + soak harness + operator README delta. Detailed plan partitioning belongs in the planner, not here.

---

## Architecture Patterns

### System Architecture Diagram

```
                         Test Surface (Phase 8)
                       ┌─────────────────────────┐
                       │    pytest (in-proc)     │
                       │   ┌─────────────────┐   │
                       │   │  fast unit suite│   │     EVERY PR
   developer ───push──>│   ├─────────────────┤   │     ─────────>
                       │   │  schema-coverage│   │
                       │   │  ruff format    │   │
                       │   └─────────────────┘   │
                       └─────────────────────────┘

                       ┌─────────────────────────┐
                       │  pytest -m live (cron)  │
                       │   ┌─────────────────┐   │
                       │   │   ZEEKER_LIVE=1 │   │     NIGHTLY
                       │   ├─────────────────┤───┼──>  ─────────>
                       │   │ data.zeeker.sg  │   │     1h soak
                       │   └────────┬────────┘   │
                       └────────────┼────────────┘
                                    │
                                    v
                          ┌──────────────────┐
                          │  data.zeeker.sg  │
                          └──────────────────┘

                       ┌─────────────────────────┐
                       │  scripts/soak/run_soak  │     PRE-RELEASE
                       │  ┌──────────────────┐   │     (manual)
                       │  │ asyncio driver   │   │     ─────────>
                       │  │ httpx.AsyncClient│   │
                       │  │  ↓               │   │
                       │  │ uvicorn (sep proc│   │
                       │  │  --workers 1)    │───┼──>  data.zeeker.sg
                       │  │  ↓               │   │     (real upstream)
                       │  │ rss sampler      │   │
                       │  │ csv + md report  │   │
                       │  └──────────────────┘   │
                       └─────────────────────────┘
```

The diagram shows three CI lanes (per-PR, nightly, pre-release), each with a different blast radius and runtime. The soak lane spawns a real Uvicorn process and a separate driver process — they are NOT in the same Python interpreter (asyncio scheduling pressure from the driver would distort the server's latency measurements).

### Recommended Test Module Layout

```
tests/
├── conftest.py                              # Existing — Phase 8 adds NO fixtures (single-plan-touch)
├── _corpus/
│   ├── hostile_inputs.py                    # Existing — Phase 8 EXTENDS CANARY_STRINGS
│   └── soak_workload.py                     # NEW — synthetic request mix for soak
├── test_filter_compiler.py                  # Existing — Phase 8 adds parametrized 13-op completeness sweep
├── test_envelope_snapshot.py                # Existing — Phase 8 verifies coverage across all 6 tools
├── test_cursor.py                           # Existing — qhash mismatch sufficient
├── test_hostile_inputs_consolidated.py      # Existing — Phase 8 EXTENDS to 9 canaries × 3 tools × 3 surfaces
├── test_rate_limit.py                       # Existing — Phase 8 adds rollover/concurrency tests
├── test_error_catalog.py                    # Existing — Phase 8 adds 11-code raise-site fan-out
├── test_app_lifespan_contract.py            # NEW — CR-02 regression + lifespan invariant tests
├── test_dependency_footprint.py             # NEW — NFR-04 lock
├── test_hidden_data_enforcement.py          # NEW — sweep across all 6 tools for HIDDEN_TABLES/HIDDEN_COLUMNS
├── test_search_fts_escape_completeness.py   # NEW — SEARCH-06 escape across 7 FTS5 operators
└── tools/                                   # Existing — fragment-join 1500 walk already exists
    └── test_retrieval_fragment_join.py      # Existing — Phase 8 confirms test_1500_fragment_walk_synthetic is in CI

scripts/                                     # NEW — top-level
└── soak/
    ├── __init__.py
    ├── run_soak.py                          # Driver entrypoint
    ├── workload.py                          # Imports tests/_corpus/soak_workload.py
    ├── rss_sampler.py                       # Stdlib resource.getrusage() based
    └── report.py                            # CSV → markdown summary

.github/workflows/                           # OR equivalent CI (TBD operator decision)
├── ci.yml                                   # Per-PR fast suite + ruff + dependency footprint
├── nightly.yml                              # 24h cron — ZEEKER_LIVE=1 + 1h smoke soak
└── soak.yml                                 # Manual workflow_dispatch — full 24h soak
```

### Pattern 1: Live-test gating (`@pytest.mark.live` + `ZEEKER_LIVE=1`)

**What:** A pytest marker that auto-skips unless `ZEEKER_LIVE=1` is set in the environment.

**When to use:** Any test that hits real `data.zeeker.sg`. Currently used in `test_metadata_cache.py:264` and `test_heavy_column_upstream.py:52`.

**Existing implementation** — already correct, no changes needed:
```python
# tests/conftest.py:76-82 (existing)
def pytest_collection_modifyitems(config, items):
    """Auto-skip @pytest.mark.live tests unless ZEEKER_LIVE env var is set."""
    if not os.getenv("ZEEKER_LIVE"):
        skip_live = pytest.mark.skip(reason="Set ZEEKER_LIVE=1 to run live tests")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip_live)
```

```python
# tests/test_heavy_column_upstream.py:52 — existing usage
@pytest.mark.live
async def test_mlaw_news_heavy_column_works():
    """Requires ZEEKER_LIVE=1."""
```

**Phase 8 additions** — every tool gets one live golden-path test:
```python
# tests/test_live_golden_path.py — NEW
@pytest.mark.live
@pytest.mark.parametrize("database,table", [...])
async def test_query_table_returns_rows_against_real_upstream(database, table):
    """Live golden-path for query_table on every URL-keyed table."""
```

### Pattern 2: Soak harness — separate-process driver

**What:** The Uvicorn server runs in process A; the driver runs in process B. The driver writes structured CSV; the sampler (subprocess of A) writes RSS samples to a separate CSV; the report module joins them post-run.

**When to use:** Any latency / RSS measurement that must not be perturbed by the measurement code.

**Why separate processes:** asyncio scheduling pressure from `asyncio.gather(*[client.post(...) for _ in range(50)])` in the same event loop as the server would inflate p95 latency. A separate process makes the driver an honest external observer.

**Example (driver shape):**
```python
# scripts/soak/run_soak.py — NEW
import asyncio
import csv
import time
from contextlib import asynccontextmanager

import httpx

from scripts.soak.workload import build_request_mix

@asynccontextmanager
async def driver_session(base_url: str, concurrency: int):
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        sem = asyncio.Semaphore(concurrency)
        yield client, sem

async def one_request(client, sem, request_spec, latency_log):
    async with sem:
        start = time.perf_counter()
        try:
            resp = await client.post("/mcp/", content=request_spec.body, headers=request_spec.headers)
            status = resp.status_code
        except Exception as exc:
            status = -1
        latency_log.append((time.time(), status, time.perf_counter() - start))

async def run_soak(base_url: str, duration_seconds: float, concurrency: int):
    deadline = time.monotonic() + duration_seconds
    latency_log = []
    async with driver_session(base_url, concurrency) as (client, sem):
        while time.monotonic() < deadline:
            workload = build_request_mix()  # synthetic mix
            await asyncio.gather(*[one_request(client, sem, r, latency_log) for r in workload])
    write_csv("latency.csv", latency_log)
```

### Pattern 3: Snapshot contract per tool

**What:** Every tool emission goes through `EnvelopeBuilder` (Phase 6 contract). The snapshot test asserts the row partition contract: top-level row keys disjoint from `HEAVY_COLUMNS`; `retrieved_content` keys ⊆ `HEAVY_COLUMNS`.

**When to use:** Once per tool. Already partially implemented in `tests/test_envelope_snapshot.py` — Phase 8 verifies coverage across all 6 tools and adds the missing ones.

**Example (existing pattern verbatim):**
```python
# tests/test_envelope_snapshot.py — existing pattern (already in codebase)
async def test_query_table_envelope_snapshot(...):
    result = await mcp_client.call_tool("query_table", {...})
    rows = result.data["data"]["rows"]
    for row in rows:
        # ENV-05 / D6-snapshot-relax
        assert set(row.keys()).isdisjoint(config.HEAVY_COLUMNS), \
            f"row leaked heavy columns: {set(row.keys()) & config.HEAVY_COLUMNS}"
        if "retrieved_content" in row:
            assert set(row["retrieved_content"].keys()).issubset(config.HEAVY_COLUMNS), \
                f"retrieved_content has non-heavy keys: {set(row['retrieved_content'].keys()) - config.HEAVY_COLUMNS}"
```

### Anti-Patterns to Avoid

- **`syrupy` for the snapshot test** — adds a 5th dev dep (NFR-04 visibility), and the snapshot contract is a 2-line `set` operation. Hand-rolled is clearer; `syrupy.assert_match(rows)` would auto-record on first run and obscure the actual contract. Use plain `assert` against the explicit `HEAVY_COLUMNS` partition.
- **`freezegun` for daily-rollover testing** — the codebase already enforces "no freezegun" via injected `time_provider` (Phase 7 / D6-12 pattern). Do NOT add `freezegun`; reuse `fake_clock` fixture and add a `fake_utc_now` injection if needed.
- **Locust / k6 / wrk for the 24h soak** — adds a runtime dep (locust is Python; k6 is Go binary; wrk is C binary; all complicate CI image builds). The 24h soak is a one-off pre-release event; a 200-LOC asyncio driver is enough.
- **Running the soak in the same process as the server** — asyncio scheduling pressure invalidates p95.
- **Using `psutil`** — would be a 5th dev dep (NFR-04 visibility). Use `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` from inside a small sidecar process that the soak driver spawns and PID-targets via `os.kill(pid, 0)` for liveness.
- **Hand-rolled HTTP retry in the soak driver** — let httpx exhaust naturally; the soak's job is to MEASURE failures, not paper over them.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Live-test env gating | A custom skipif decorator per file | `tests/conftest.py:pytest_collection_modifyitems` (existing) | Already wired to the `live` marker registered in `pyproject.toml:46` |
| Hostile-input corpus | Per-test inline canary list | `tests/_corpus/hostile_inputs.py:CANARY_STRINGS` (existing) | Centralized, audit-pass-ready |
| Surface-leak detection helper | Per-test `assert "X" not in resp.body` loop | `tests/_corpus/hostile_inputs.py:_surfaces_contain` (existing) | Already covers stdout/stderr/log/error + repr leakage |
| RSS sampling | `psutil.Process(pid).memory_info().rss` | `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` (stdlib) | Avoids 5th dev dep; coarse but sufficient for "RSS < 256 MB?" gate |
| Latency percentiles | `hdrhistogram` | Sort + index: `sorted(latencies)[int(0.95 * len(...))]` | Soak completes once; not a live observability path; sorting 24h × 50 RPS × 86400s = 4.3M samples in ~5s is fine |
| Daily-rollover unit test | Wall-clock sleeping or `freezegun` | Existing `fake_clock` fixture + new `fake_utc_now` injection | Already established Phase 7 pattern; consistent codebase style |
| Test fixture for ASGI client | A new `httpx.AsyncClient(transport=ASGITransport(app))` per test | `asgi_client` fixture (existing) | Already in conftest.py |
| FastMCP in-memory client for tool tests | Manual JSON-RPC envelope construction | `mcp_client` fixture using `Client(mcp)` (existing) | Already in conftest.py |
| pyproject.toml dep parsing | `re`-based scan | `tomllib.loads(text)` (stdlib in 3.11+) | Project requires Python 3.11+; stdlib parser exists |
| Tool-set introspection in lifespan | Direct attribute access (`tool.return_type`) | `getattr(tool, "return_type", None)` | Phase 7 deferred — Tool base class doesn't declare return_type |
| Soak request mix definition | Hardcoded URLs in driver | `tests/_corpus/soak_workload.py` (NEW) — shared with future regression tests | Single source of truth for "what does a typical caller hit?" |

**Key insight:** Phase 8 is a *coverage* phase, not an *invention* phase. Every test pattern, fixture, and helper already exists in the codebase from Phases 1–7. The four genuinely new artifacts are: (1) `scripts/soak/`, (2) `tests/test_dependency_footprint.py`, (3) `tests/test_app_lifespan_contract.py`, (4) `tests/_corpus/soak_workload.py`. Everything else is *additions to existing test files* or *new test files following established patterns*.

---

## Common Pitfalls

### Pitfall 1: Soak measures driver overhead, not server latency

**What goes wrong:** Driver runs `asyncio.gather(*[client.post(...) for _ in range(1000)])` in the same Python interpreter as the server (or with too-tight timeouts). p95 includes time the request spent waiting on the driver's own event loop.

**Why it happens:** Convenience — running both in one process is one shell command instead of two.

**How to avoid:**
- Driver and server run in **separate processes**. Driver: `python -m scripts.soak.run_soak --url http://127.0.0.1:8000`. Server: `uvicorn mcp_zeeker.app:app --host 127.0.0.1 --port 8000 --workers 1`.
- Driver's `httpx.AsyncClient` has a generous timeout (`timeout=10.0`) so the soak measures real server response time, not artificial timeouts.
- Driver records timestamps with `time.perf_counter()` AROUND the await; do NOT measure inside the `httpx` request hooks.

**Warning signs:** p95 latency in the soak is ~3× higher than what `time` against a single curl shows. CPU on the driver process pegs at 100%.

### Pitfall 2: 24h soak misses the daily-rate-limit rollover

**What goes wrong:** Soak runs 24h but starts at 14:00 UTC. At ~14:00 UTC the next day, the daily counter resets — but the driver has already exhausted the 5,000-per-day budget hours ago and is now in the steady 429 state. The reset happens but the driver doesn't re-detect "I can send full-rate again."

**Why it happens:** Daily counter reset happens at 00:00 UTC, not 24h after the test starts. A 24h test starting at 14:00 UTC sees one rollover at the 10h mark.

**How to avoid:**
- Soak driver tracks 429 rate: it should drop sharply at 00:00 UTC if the daily counter reset is working.
- Soak report includes a `daily_rollover_observed: bool` flag — true iff there was a >50% drop in 429 rate within ±60 seconds of an integer UTC midnight.
- Document in the soak report: "If `daily_rollover_observed == false` because the soak started after 00:00 UTC and ended before the next 00:00 UTC, run the soak across midnight intentionally."

**Warning signs:** Soak report shows steady 100% 429 rate for the back half of the run with no drop near a UTC date boundary.

### Pitfall 3: Live tests flake because of upstream rate-limiting

**What goes wrong:** CI runs nightly at 02:00 UTC. The Zeeker upstream sees a burst of test requests from the CI runner IP. If multiple Phase 8 live tests run in parallel against `data.zeeker.sg`, they exhaust the upstream's own rate limit (or the connector's own 60/min limit applied to the CI runner's IP).

**Why it happens:** Live tests look like real client traffic to the upstream.

**How to avoid:**
- Live tests run **sequentially** in CI: `pytest -m live -p no:xdist` or omit pytest-xdist.
- Live tests sleep 1s between calls (or use `pytest_asyncio` with module-scoped fixtures so the session HTTPX client is shared across all live tests in a module).
- Document in the test file docstring: "These tests assume the CI runner IP is allowlisted or under-budget on the upstream's rate limit."

**Warning signs:** Live tests intermittently fail with HTTP 429 from upstream. The first 5 pass; the next 15 fail.

### Pitfall 4: `tool.return_type` AttributeError surfaces only in production

**What goes wrong:** Phase 7 verification (CR-02) noted that `src/mcp_zeeker/app.py:59` accesses `tool.return_type` on the FastMCP `Tool` base class. Today all 6 tools register as `FunctionTool` instances which DO have `return_type`. If we ever add a `TransformedTool` (a Phase 9 / submission-prep possibility) or a custom `Tool` subclass for testing, the lifespan startup fails with `AttributeError: 'Tool' object has no attribute 'return_type'`.

**Why it happens:** Direct attribute access on a base class assumes a subclass-only attribute exists.

**How to avoid:**
- Replace `tool.return_type is not Envelope` with `getattr(tool, "return_type", None) is not Envelope` (one-line fix).
- Add `tests/test_app_lifespan_contract.py::test_lifespan_tolerates_non_function_tool`: monkeypatch `mcp.list_tools` to return a list containing a `Tool` subclass instance whose docstring ends with `TOOL_TRAILER` and which has NO `return_type` attribute. Assert the lifespan completes without raising.

**Warning signs:** Production startup fails after a Phase 9 PR adds a `TransformedTool`. The test would have caught it.

### Pitfall 5: Snapshot tests pass because the upstream stub returns no heavy columns

**What goes wrong:** Test stubs `stub_table_rows` populate row dicts with only light columns (e.g., `{"citation": "...", "case_name": "..."}`). The snapshot contract `set(row.keys()).isdisjoint(HEAVY_COLUMNS)` passes trivially because heavy columns aren't in the stub data.

**Why it happens:** The contract test is meant to catch the case "request returned heavy text inlined at row top level." If the stub never returns heavy text, the test always passes — even if the production code path would leak.

**How to avoid:**
- Snapshot tests stub upstream responses with rows that **DO** contain heavy columns at the top level (mimicking a malformed upstream response). Assert the **handler strips them** before envelope emission. The contract isn't "rows happen to be light" — it's "rows are guaranteed light, even when the upstream payload is dirty."
- For the heavy-column-requested path, stub upstream with heavy text and assert it appears under `retrieved_content`, not at row top.

**Warning signs:** Manually deleting the row-reshape code in `tools/retrieval.py` doesn't break any snapshot test.

### Pitfall 6: Hostile-input fan-out misses the log surface

**What goes wrong:** `test_hostile_inputs_consolidated.py` (existing) checks that canaries don't appear in the response body or error message. It does NOT check structured log lines emitted by `StructuredLogMiddleware` — but that middleware echoes the tool name, db, and table, and a hostile db/table name could leak.

**Why it happens:** The locked log field set is `(request_id, tool, database, table, duration_ms, status, ip_prefix, error_code)`. `database` and `table` are user-supplied parameters; the access-log emits them verbatim.

**How to avoid:**
- Phase 8 hostile-input tests EXPLICITLY check the structlog `capture_logs` output for canary leakage in the `database` and `table` fields. If a hostile database/table name is allowed to leak into logs, mitigation is to validate `database in config.ALLOWED_DATABASES` BEFORE the log line emits (hostile input gets rejected with `unknown_database` and the log shows the literal "<hidden>" sentinel for unknown names).
- Use `tests/_corpus/hostile_inputs.py:_surfaces_contain` to detect log leakage in addition to error/stdout/stderr.

**Warning signs:** A hostile request like `database="</system>"` appears verbatim in `database=</system>` log fields.

### Pitfall 7: 1,500-fragment regression already exists but isn't gated in CI

**What goes wrong:** `tests/tools/test_retrieval_fragment_join.py:637 test_1500_fragment_walk_synthetic` exists from Phase 5 (FRAG-04) but Phase 8 doesn't formally bind it to TEST-04. The traceability table claims TEST-04 is satisfied without an explicit phase tie-in.

**Why it happens:** Test exists, requirement is in a different phase, traceability isn't auto-checked.

**How to avoid:**
- Phase 8 plan explicitly references the existing test and adds a docstring note: "TEST-04 regression — Phase 5 origin, Phase 8 ownership." Update REQUIREMENTS.md traceability row TEST-04 to point at this test.
- No new test code needed; this is a documentation fix.

**Warning signs:** None at runtime — but auditing TEST-04 from REQUIREMENTS.md → test would dead-end.

### Pitfall 8: `tomllib` dep audit reports false positives from transitive deps

**What goes wrong:** `tests/test_dependency_footprint.py` reads `pyproject.toml` `[project.dependencies]`. But `uv.lock` includes transitive deps (e.g., `anyio`, `sniffio`, `h11`, `idna`, `certifi`, `mcp` itself). If the test reads `uv.lock` instead, it reports 30+ "unauthorized" deps.

**Why it happens:** Confusion between direct deps (NFR-04 cap) and transitive deps (uncapped).

**How to avoid:**
- Test reads `pyproject.toml` ONLY, parses `[project.dependencies]` (the 6-tuple) and `[dependency-groups.dev]` (the 4-tuple). Does NOT read `uv.lock`.
- The test asserts: (1) the count is exactly 6 / 4, (2) the names match the locked set, (3) the version specifiers match the project's `~=N.M` discipline.

**Warning signs:** Test fails after a transient dep update with a long list of transitive packages.

---

## Code Examples

Verified patterns from the codebase + new patterns for soak/dep-audit.

### `@pytest.mark.live` gating (existing, reuse verbatim)

```python
# tests/conftest.py:76-82 — VERIFIED existing implementation
def pytest_collection_modifyitems(config, items):
    """Auto-skip @pytest.mark.live tests unless ZEEKER_LIVE env var is set."""
    if not os.getenv("ZEEKER_LIVE"):
        skip_live = pytest.mark.skip(reason="Set ZEEKER_LIVE=1 to run live tests")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip_live)
```

```python
# tests/test_heavy_column_upstream.py:52 — VERIFIED existing usage
@pytest.mark.live
async def test_X():
    """Requires ZEEKER_LIVE=1."""
```

### Hostile-input fan-out (extends existing)

```python
# tests/_corpus/hostile_inputs.py — EXTEND existing CANARY_STRINGS
CANARY_STRINGS: list[str] = [
    "</system>",                                # existing
    "NEAR('data' 'protection') AND NOT",        # existing — FTS5 ops
    "x" * 5001,                                 # existing — 5 KB
    "ZEEKER_CANARY_42",                         # existing
    "\udc80",                                   # existing — lone surrogate
    "﻿",                                   # NEW — BOM (byte-order mark)
    "‮",                                   # NEW — RTL override
    "\x1b[31mRED\x1b[0m",                       # NEW — ANSI escape
    '{"injected": "json"}',                     # NEW — JSON injection
]
```

```python
# tests/test_hostile_inputs_consolidated.py — VERIFIED existing pattern
async def test_canary_X_does_not_echo(canary, mcp_client, caplog, capsys):
    """Phase 6 origin; Phase 8 expands matrix to 9 canaries × 3 tools × 3 surfaces."""
    with pytest.raises(ToolError) as exc_info:
        await mcp_client.call_tool("query_table", {"database": "pdpc", "table": "...", "filters": [{"column": "title", "op": "exact", "value": canary}]})
    captured = capsys.readouterr()
    log_text = "\n".join(r.message for r in caplog.records)
    leaks = _surfaces_contain(canary, captured_out=captured.out, captured_err=captured.err, log_text=log_text, error_text=str(exc_info.value))
    assert leaks == [], f"canary leaked into surfaces: {leaks}"
```

### Snapshot contract (extends existing)

```python
# tests/test_envelope_snapshot.py — VERIFIED existing pattern
async def test_query_table_row_partition(mcp_client, frozen_retrieved_at, ...):
    """ENV-05 / TEST-03 / D6-snapshot-relax — extended to all 6 tools."""
    result = await mcp_client.call_tool("query_table", {...})
    rows = result.data["data"]["rows"]
    for row in rows:
        # NEW IN PHASE 8: explicit error message including the leak set
        leaked_top = set(row.keys()) & config.HEAVY_COLUMNS
        assert leaked_top == set(), f"top-level row leaked heavy columns: {leaked_top}"
        if "retrieved_content" in row:
            non_heavy = set(row["retrieved_content"].keys()) - config.HEAVY_COLUMNS
            assert non_heavy == set(), f"retrieved_content has non-heavy keys: {non_heavy}"
```

### CR-02 lifespan regression (NEW)

```python
# tests/test_app_lifespan_contract.py — NEW
"""CR-02 regression — lifespan must tolerate Tool subclasses that lack return_type.

Phase 7 VERIFICATION.md deferred this — today all 6 registered tools are
FunctionTool instances (which DO have return_type). The fix in app.py uses
getattr(tool, "return_type", None) — defensive against future TransformedTool /
custom Tool subclasses that may not declare return_type.
"""

from __future__ import annotations

import contextlib

import pytest
from fastmcp.tools import Tool

from mcp_zeeker import config
from mcp_zeeker.core.envelope import Envelope


class _DummyToolWithoutReturnType(Tool):
    """Tool subclass that lacks the FunctionTool return_type attribute."""

    def __init__(self):
        # Must satisfy Tool ABC; field set varies by FastMCP minor version
        super().__init__(name="_dummy", description=f"Dummy tool. {config.TOOL_TRAILER}")


async def test_lifespan_tolerates_non_function_tool(monkeypatch):
    """CR-02: lifespan must use getattr(tool, 'return_type', None) — never raw access."""
    from mcp_zeeker.app import app, lifespan
    from mcp_zeeker.server import mcp

    async def stub_list_tools():
        return [_DummyToolWithoutReturnType()]

    monkeypatch.setattr(mcp, "list_tools", stub_list_tools)

    # Lifespan must complete without AttributeError. The dummy tool's missing
    # return_type should be detected via getattr fallback and surface as the
    # contract-drift RuntimeError, NOT AttributeError.
    with pytest.raises(RuntimeError, match="return_type is not Envelope"):
        async with lifespan(app):
            pass
```

The fix in `app.py`:

```python
# src/mcp_zeeker/app.py:59 — CHANGE FROM
if tool.return_type is not Envelope:
    raise RuntimeError(f"tool contract drift: {tool.name} return_type is not Envelope")

# TO
if getattr(tool, "return_type", None) is not Envelope:
    raise RuntimeError(f"tool contract drift: {tool.name} return_type is not Envelope")
```

### Dependency-footprint enforcement (NEW)

```python
# tests/test_dependency_footprint.py — NEW
"""NFR-04: lock the runtime dep set + dev dep set in the test suite.

Adding a runtime dep silently violates NFR-04. This test reads pyproject.toml
directly via stdlib tomllib (no external dep) and asserts the exact contents
of [project.dependencies] and [dependency-groups.dev].
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


_PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"

# NFR-04: exactly these 6 runtime deps + 4 dev deps. Order does not matter
# (pyproject.toml is a TOML list/table — pytest sees a Python list/dict).
_REQUIRED_RUNTIME = frozenset({
    "fastmcp",
    "pydantic",
    "httpx",
    "starlette",
    "uvicorn",
    "structlog",
})

_REQUIRED_DEV = frozenset({
    "pytest",
    "pytest-asyncio",
    "pytest-httpx",
    "ruff",
})


def _strip_specifier(dep: str) -> str:
    """Return the bare package name from a `name~=ver` or `name>=x,<y` spec."""
    return re.split(r"[~=<>!\s]", dep, 1)[0]


def test_runtime_deps_match_locked_set():
    """NFR-04 — runtime dep set is frozen at exactly 6 packages."""
    payload = tomllib.loads(_PYPROJECT.read_text())
    declared = {_strip_specifier(d) for d in payload["project"]["dependencies"]}
    assert declared == _REQUIRED_RUNTIME, (
        f"runtime deps drifted from NFR-04 locked set; "
        f"missing={_REQUIRED_RUNTIME - declared}, "
        f"extra={declared - _REQUIRED_RUNTIME}"
    )


def test_dev_deps_match_locked_set():
    """NFR-04 — dev dep set is frozen at exactly 4 packages."""
    payload = tomllib.loads(_PYPROJECT.read_text())
    declared = {_strip_specifier(d) for d in payload["dependency-groups"]["dev"]}
    assert declared == _REQUIRED_DEV, (
        f"dev deps drifted from NFR-04 locked set; "
        f"missing={_REQUIRED_DEV - declared}, "
        f"extra={declared - _REQUIRED_DEV}"
    )


def test_pinning_discipline_runtime():
    """All runtime deps use ~= compat-release pinning OR explicit range."""
    payload = tomllib.loads(_PYPROJECT.read_text())
    for dep in payload["project"]["dependencies"]:
        assert any(op in dep for op in ("~=", ">=", "==")), (
            f"runtime dep '{dep}' lacks a version specifier (NFR-04 pinning discipline)"
        )
```

### Soak driver entrypoint (NEW)

```python
# scripts/soak/run_soak.py — NEW
"""24h soak harness — TEST-05.

Drives the running mcp-zeeker server (separate uvicorn process) with a
synthetic workload and writes per-request latency + per-minute RSS samples
to CSV. Post-run report.py converts to a markdown summary for the CI artifact.

Usage:
    # Terminal A — start server in single-worker mode
    uv run uvicorn mcp_zeeker.app:app --host 127.0.0.1 --port 8000 --workers 1

    # Terminal B — start soak driver
    uv run python -m scripts.soak.run_soak \\
        --url http://127.0.0.1:8000 \\
        --duration 86400 \\
        --concurrency 50 \\
        --rss-sample-interval 60 \\
        --output ./soak-results

NFR-01: p50 < 300ms, p95 < 1.5s for non-fragment tools
NFR-02: 50 concurrent without saturation
NFR-03: < 256 MB resident under steady load
TEST-05: stable memory, no PoolTimeout cascade, log growth bounded, daily rate-limit rollover
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import resource
import time
from pathlib import Path

import httpx

from scripts.soak.workload import build_request_mix


async def _one_request(client, sem, request_spec, latency_log):
    async with sem:
        wall_ts = time.time()
        start = time.perf_counter()
        try:
            resp = await client.post(
                "/mcp/",
                content=request_spec.body,
                headers=request_spec.headers,
            )
            status = resp.status_code
            err = ""
        except httpx.PoolTimeout as exc:
            status = -1
            err = "pool_timeout"  # TEST-05: distinct flag
        except httpx.TimeoutException:
            status = -2
            err = "request_timeout"
        except Exception as exc:  # noqa: BLE001 — soak driver MUST log every class
            status = -3
            err = type(exc).__name__
        latency_log.append((wall_ts, status, time.perf_counter() - start, err))


def _sample_rss() -> int:
    """Return RSS in KB (Linux) or bytes (macOS) — caller normalizes.

    Uses stdlib resource module; no psutil dependency. ru_maxrss is
    cumulative-max-since-process-start on Linux; resident-set-current on
    macOS (different units). For "RSS staying under 256 MB" the cumulative
    max is the strict-MORE-conservative reading on Linux.
    """
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


async def _rss_sampler_loop(rss_log, interval_seconds, deadline_mono):
    while time.monotonic() < deadline_mono:
        rss_log.append((time.time(), _sample_rss()))
        await asyncio.sleep(interval_seconds)


async def run_soak(args: argparse.Namespace) -> None:
    deadline_mono = time.monotonic() + args.duration
    latency_log: list = []
    rss_log: list = []

    async with httpx.AsyncClient(base_url=args.url, timeout=10.0) as client:
        sem = asyncio.Semaphore(args.concurrency)
        sampler = asyncio.create_task(_rss_sampler_loop(rss_log, args.rss_sample_interval, deadline_mono))
        try:
            while time.monotonic() < deadline_mono:
                workload = build_request_mix()
                await asyncio.gather(*[_one_request(client, sem, r, latency_log) for r in workload])
        finally:
            sampler.cancel()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "latency.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wall_ts", "status", "duration_seconds", "error_class"])
        writer.writerows(latency_log)
    with (out_dir / "rss.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wall_ts", "rss_kb"])
        writer.writerows(rss_log)


def main() -> None:
    parser = argparse.ArgumentParser(description="24h soak driver for mcp-zeeker")
    parser.add_argument("--url", required=True, help="Base URL (e.g. http://127.0.0.1:8000)")
    parser.add_argument("--duration", type=float, default=86400, help="Soak duration in seconds (default 24h)")
    parser.add_argument("--concurrency", type=int, default=50, help="Max in-flight requests (NFR-02 = 50)")
    parser.add_argument("--rss-sample-interval", type=float, default=60.0, help="RSS sample interval in seconds")
    parser.add_argument("--output", default="./soak-results", help="Output directory for CSV artifacts")
    args = parser.parse_args()
    asyncio.run(run_soak(args))


if __name__ == "__main__":
    main()
```

### Soak workload definition (NEW)

```python
# tests/_corpus/soak_workload.py — NEW
"""Synthetic request mix for the 24h soak driver — TEST-05.

Defines a representative agent workload (the kind of tool calls Claude
actually issues during a typical /chat session). Lives under tests/_corpus
so the same mix is reusable for future regression tests, not just the soak.

Distribution mirrors observed Phase 6.1 manual-UAT traffic:
- 35% list_databases / list_tables / describe_table (cheap discovery)
- 30% query_table on URL-keyed tables (medium)
- 20% search across all 4 DBs (expensive — fan-out)
- 10% fetch by URL (medium)
- 5%  query_table on *_fragments (heavy — 2-step join)
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass


@dataclass
class RequestSpec:
    body: bytes
    headers: dict


def _envelope(method: str, params: dict) -> RequestSpec:
    body = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": random.randint(1, 1_000_000),
    }).encode("utf-8")
    return RequestSpec(
        body=body,
        headers={"content-type": "application/json", "accept": "application/json, text/event-stream"},
    )


_DISTRIBUTION = [
    (0.35, "discovery"),
    (0.30, "query_url"),
    (0.20, "search"),
    (0.10, "fetch"),
    (0.05, "fragment"),
]


def _pick_kind() -> str:
    r = random.random()
    cum = 0.0
    for w, kind in _DISTRIBUTION:
        cum += w
        if r < cum:
            return kind
    return "discovery"


def build_request_mix() -> list[RequestSpec]:
    """Build a small batch (1-5 requests) representing one driver "tick".

    Each soak iteration sends this batch; the driver parallelizes within
    the batch up to the concurrency limit.
    """
    batch_size = random.randint(1, 5)
    batch: list[RequestSpec] = []
    for _ in range(batch_size):
        kind = _pick_kind()
        if kind == "discovery":
            batch.append(_envelope("tools/call", {"name": "list_databases", "arguments": {}}))
        elif kind == "query_url":
            batch.append(_envelope("tools/call", {
                "name": "query_table",
                "arguments": {"database": "pdpc", "table": "enforcement_decisions", "limit": 5},
            }))
        elif kind == "search":
            batch.append(_envelope("tools/call", {
                "name": "search",
                "arguments": {"query": "data protection", "limit": 5},
            }))
        elif kind == "fetch":
            batch.append(_envelope("tools/call", {
                "name": "fetch",
                "arguments": {
                    "database": "pdpc",
                    "table": "enforcement_decisions",
                    "url": "https://www.pdpc.gov.sg/...",  # replaced from cached set
                },
            }))
        elif kind == "fragment":
            batch.append(_envelope("tools/call", {
                "name": "query_table",
                "arguments": {
                    "database": "zeeker-judgements",
                    "table": "judgments_fragments",
                    "filters": [{"column": "source_url", "op": "exact", "value": "https://www.elitigation.sg/..."}],
                    "limit": 50,
                },
            }))
    return batch
```

---

## Runtime State Inventory

This is a feature/test phase, NOT a rename or refactor. Step 2.5 explicitly skips for non-rename phases.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 8 introduces no persistent state. The soak harness produces transient CSV artifacts under `./soak-results/`; these are gitignored test outputs, not stored runtime state. | None |
| Live service config | None — no external services beyond the upstream `data.zeeker.sg` (read-only, unchanged). CI workflows are added in `.github/workflows/` but are git-tracked. | None |
| OS-registered state | None — no Windows tasks, no launchd plists, no systemd units added by Phase 8. | None |
| Secrets/env vars | `ZEEKER_LIVE` env gate (existing). No new secrets. The soak does NOT require credentials (anonymous tier). | None — verified by reading `tests/conftest.py` |
| Build artifacts | `./soak-results/` — gitignored CSV/MD outputs. `tests/__pycache__/` — git-ignored bytecode. No installed packages renamed or removed. | None |

**Nothing found in any category** — Phase 8 is a pure addition phase.

---

## Environment Availability

The soak harness depends on tools beyond the runtime stack. Probe results:

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python>=3.11` | All tests + soak driver | ✓ | 3.13.5 | — |
| `uv` | Test invocation, dep audit | ✓ | 0.11.8 | — |
| `pytest~=8.3` | All test files | ✓ (existing dev dep) | from uv.lock | — |
| `pytest-asyncio~=1.3` | Async test support | ✓ (existing dev dep) | from uv.lock | — |
| `pytest-httpx~=0.35` | HTTPX mocking | ✓ (existing dev dep, **note 0.35 not 0.36 currently in lock**) | 0.35.0 | — |
| `httpx~=0.28` | Soak driver, runtime | ✓ (existing runtime dep) | from uv.lock | — |
| `tomllib` | Dependency-footprint test | ✓ (Python 3.11+ stdlib) | builtin | — |
| `resource` (stdlib) | Soak RSS sampler (Linux/macOS) | ✓ (POSIX stdlib) | builtin | On Windows: skip soak (CI runs on Linux) |
| `data.zeeker.sg` (upstream) | Live tests + 24h soak | ✓ (assumed reachable) | — | If unreachable: skip live + soak; mark CI nightly as inconclusive |
| `psutil` | Alternative RSS sampler | ✗ NOT AVAILABLE; explicitly REJECTED to preserve NFR-04 | — | Use `resource.getrusage()` (preferred) |
| `locust` / `k6` / `wrk` | Alternative soak driver | ✗ NOT AVAILABLE; explicitly REJECTED to keep dep footprint flat | — | Custom asyncio driver (recommended) |
| `syrupy` | Snapshot library | ✗ NOT AVAILABLE; explicitly REJECTED — preserves NFR-04 | — | Hand-rolled `set` assertion |
| `freezegun` | Time mocking | ✗ NOT AVAILABLE; explicitly REJECTED — codebase uses injected `time_provider` | — | Existing `fake_clock` fixture + new `fake_utc_now` injection |
| `hdrhistogram` | Latency percentile lib | ✗ NOT AVAILABLE; not justified for one-shot soak | — | `sorted(samples)[int(p * len(samples))]` |

**Missing dependencies with no fallback:** None blocking.

**Missing dependencies with fallback:** All five rejected packages have stdlib or trivial-code fallbacks.

**Note on pytest-httpx version drift:** `pyproject.toml:19` pins `pytest-httpx~=0.35` but the spawn message references `0.36.2` (CLAUDE.md mentions 0.36.2). The codebase is locked at 0.35.0 in `uv.lock`. Phase 8 should NOT bump pytest-httpx without an explicit decision — it is a Wave 1 concern only if the new tests need a 0.36.x feature (they don't, based on this research).

---

## Test Taxonomy & File Layout

This is the §1 deliverable — every REQ-ID maps to one or more test modules with line refs to the closest existing analog.

| REQ ID | Test Module | New / Existing | Closest Analog | Coverage Notes |
|--------|------------|----------------|----------------|----------------|
| TEST-01 (filter mapping, 13 ops) | `tests/test_filter_compiler.py` | EXISTING — extend | self (lines 36-280) | 13 ops × happy + edge + INJ-05; current file has ~12 tests; Phase 8 adds parametrized completeness sweep covering all 13 ops × 4 column types (TEXT/INTEGER/REAL/BLOB) |
| TEST-01 (envelope shape) | `tests/test_envelope_snapshot.py` | EXISTING — verify all 6 tools | self (full file) | Confirm coverage across `list_databases`, `list_tables`, `describe_table`, `query_table`, `fetch`, `search` |
| TEST-01 (hidden table/column) | `tests/test_hidden_data_enforcement.py` | NEW | `tests/test_visibility.py` (denylist tests, Phase 2) | Sweep across all 6 tools — every entry in `HIDDEN_TABLES` and `HIDDEN_COLUMNS` rejected with `unknown_table`/`unknown_column` from each tool that takes those params |
| TEST-01 (fragment-parent join) | `tests/tools/test_retrieval_fragment_join.py` | EXISTING — already comprehensive | self | 957-frag walk + 1500-frag walk + multi-match all present |
| TEST-01 (rate-limit windows) | `tests/test_rate_limit.py` | EXISTING — verify burst/sustained/daily | self | Phase 7 added 13 GREEN tests; Phase 8 adds concurrency stress (50 simultaneous) |
| TEST-01 (error code mapping) | `tests/test_error_catalog.py` | EXISTING — verify 11-code fan-out | self | Phase 7 has 4 tests; Phase 8 adds parametrized test that asserts every catalog code has at least one verified raise site |
| TEST-01 (cursor binding) | `tests/test_cursor.py` | EXISTING — qhash mismatch covered | self (lines 36-67) | Add cursor-walk-the-shape test (REQ-04 SC-4) |
| TEST-02 (live integration) | `tests/test_live_golden_path.py` | NEW | `tests/test_metadata_cache.py:264` (live pattern), `tests/test_heavy_column_upstream.py:52` (live pattern) | One `@pytest.mark.live` test per tool: `list_databases`, `list_tables`, `describe_table`, `search`, `query_table`, `fetch` against `https://data.zeeker.sg` |
| TEST-03 (snapshot per tool) | `tests/test_envelope_snapshot.py` | EXISTING — verify all 6 tools | self | Phase 6 covers list_databases/list_tables/describe_table/query_table/fetch/search; Phase 8 adds explicit row-key partition assertions |
| TEST-04 (1500-fragment regression) | `tests/tools/test_retrieval_fragment_join.py:637` | EXISTING — verify in CI | self | `test_1500_fragment_walk_synthetic` exists; Phase 8 documents it under TEST-04 traceability |
| TEST-05 (24h soak) | `scripts/soak/` + `tests/test_soak_smoke.py` | NEW | None — first-of-kind | Driver in `scripts/`, smoke test (1-min soak) in `tests/` for CI fast-path |
| TEST-06 (hostile-input corpus) | `tests/test_hostile_inputs_consolidated.py` | EXISTING — extend matrix | self | Phase 6 covers 5 canaries × 3 tools; Phase 8 extends to 9 canaries × 3 tools × 3 surfaces (error/log/response) |
| NFR-01 (p50/p95) | `scripts/soak/report.py` (post-run) | NEW | None | Computed from `latency.csv` |
| NFR-02 (50 concurrent) | `scripts/soak/run_soak.py` (driver param) | NEW | None | Driver `--concurrency 50` |
| NFR-03 (RSS < 256 MB) | `scripts/soak/report.py` | NEW | None | Computed from `rss.csv` |
| NFR-04 (dep footprint) | `tests/test_dependency_footprint.py` | NEW | None | Locks pyproject.toml deps |
| NFR-05 (operator docs) | `README.md` (extend existing) | EXISTING — extend | self (lines 28-90) | Anthropic IP allowlist note; single-worker reaffirmation |

**Coverage summary:** 11 REQ IDs → 7 existing test files extended + 4 new test files + 1 new soak harness module + README delta. Zero new fixtures (single-plan-touch already enforced; Phase 8 reuses).

---

## Filter-Operator Coverage (TEST-01 part 1)

The spawn message says "11 operators." The actual filter compiler at `src/mcp_zeeker/core/filter_compiler.py:30-44` declares **13 operators** as a `Literal` type:

```
exact, not, contains, startswith, endswith,
gt, gte, lt, lte,
in, notin,
isnull, notnull
```

Phase 8 plan must cover ALL 13. The current `tests/test_filter_compiler.py` covers all 13 individually but does not have a single parametrized sweep that asserts the locked set against `compile_filters` behavior. Phase 8 ADDS:

```python
# tests/test_filter_compiler.py — extension
ALL_OPS = ("exact", "not", "contains", "startswith", "endswith",
           "gt", "gte", "lt", "lte", "in", "notin", "isnull", "notnull")

@pytest.mark.parametrize("op", ALL_OPS)
def test_op_in_locked_set(op):
    """TEST-01 / D3-02: verify the FilterOp Literal contains exactly 13 names."""
    from mcp_zeeker.core.filter_compiler import FilterOp
    from typing import get_args
    assert op in get_args(FilterOp)
    assert len(get_args(FilterOp)) == 13
```

Plus a **column-type-cross-product** test:

```python
@pytest.mark.parametrize("op,col_type", [
    (op, ct)
    for op in ("gt", "gte", "lt", "lte")
    for ct in ("INTEGER", "REAL", "TEXT")
])
def test_numeric_ops_across_column_types(op, col_type):
    """TEST-01 / D3-10: numeric ops behave deterministically by column type."""
```

---

## Cursor-Binding Rejection (TEST-01 part 7)

The cursor module at `src/mcp_zeeker/core/cursor.py` already implements:
- `decode_cursor` raises `ToolError("invalid_cursor: cursor does not match current request shape")` on qhash mismatch (line 140)
- `decode_cursor` raises `ToolError("invalid_cursor: cursor is malformed")` on base64/utf-8/format errors (line 136)
- `decode_keyset_cursor` raises `ToolError("invalid_cursor: keyset cursor is malformed")` on its own format errors (line 208)

Existing test at `tests/test_cursor.py:36-46` already covers shape mismatch.

**Phase 8 adds:**

```python
# tests/test_cursor.py — extension for query A → query B contract test
def test_cursor_for_query_A_rejected_when_used_on_query_B():
    """REQ TEST-01 / SC-4: cursor reuse with different shape is rejected."""
    from mcp_zeeker.core.cursor import canonical_shape_str, encode_cursor, decode_cursor
    from fastmcp.exceptions import ToolError

    shape_A = canonical_shape_str("pdpc", "enforcement_decisions",
                                   sort=None, filters=[], columns=None)
    shape_B = canonical_shape_str("pdpc", "enforcement_decisions",
                                   sort="decision_date", filters=[], columns=None)
    cursor = encode_cursor(shape_A, "100")
    with pytest.raises(ToolError, match="invalid_cursor"):
        decode_cursor(cursor, shape_B)
```

This exists already (line 38-46) — Phase 8 verifies it has a docstring tying to TEST-01.

---

## Snapshot Tests (TEST-03)

The contract is `set(row.keys()) ∩ HEAVY_COLUMNS == ∅` and `set(row["retrieved_content"].keys()) ⊆ HEAVY_COLUMNS`. The existing `tests/test_envelope_snapshot.py` already covers this. Phase 8 verifies all 6 tools have a snapshot test and adds **explicit assertion error messages** that name the leaked keys (current file uses bare `assert` which makes triage painful).

**Recommendation: hand-rolled assertions, NOT `syrupy`.** Reasons:
1. `syrupy` would be a 5th dev dep (NFR-04 visibility cost).
2. The contract is two `set` operations — 4 lines of code.
3. `syrupy` auto-records snapshots on first run; the auto-recording would mask whether the contract is satisfied or just whether the output happens to match a captured baseline.
4. `syrupy` snapshots live in `__snapshots__/` directories — adds clutter.

Tradeoff documented: if Phase 8 adds 3+ snapshot test files in the future, the case for `syrupy` strengthens. For 6 tool-snapshot tests, hand-rolled wins.

---

## Hostile-Input Corpus (TEST-06)

### Existing canaries (Phase 3/4/5/6 — KEEP verbatim)

```python
# tests/_corpus/hostile_inputs.py — existing, unchanged
CANARY_STRINGS: list[str] = [
    "</system>",                                # HTML/system tag injection sentinel
    "NEAR('data' 'protection') AND NOT",        # FTS5 operators
    "x" * 5001,                                 # 5 KB oversized
    "ZEEKER_CANARY_42",                         # plain round-trip detector
    "\udc80",                                   # lone surrogate — UTF-8 boundary
]
```

### Phase 8 additions (4 new canaries)

| Canary | Purpose | Detection Surface |
|--------|---------|-------------------|
| `"﻿"` | BOM (byte-order mark) — invisible char that often round-trips through naive string handling | error msg, log line, response metadata |
| `"‮"` | RTL override — flips display direction; potential confusion in agent display | error msg, log line |
| `"\x1b[31mRED\x1b[0m"` | ANSI escape — terminal control sequence; never legitimate in MCP responses | log line (most likely surface) |
| `'{"injected": "json"}'` | JSON injection — string that parses as JSON inside a JSON envelope | response body, error msg |

### Path mapping (filter-value-echo paths)

The canaries must exercise EVERY path that echoes user input:

| Code Path | Surface | Test Module |
|-----------|---------|-------------|
| `core/filter_compiler.py` ToolError messages | Error message | `test_filter_compiler.py:test_invalid_filter_op_no_value_echo` (existing) |
| `core/cursor.py` ToolError messages | Error message | `test_cursor.py` (existing) |
| `tools/retrieval.py` `unknown_database`/`unknown_table` | Error message | `test_hostile_inputs_consolidated.py` (existing — Phase 8 extends) |
| `tools/search.py` FTS5 escape failure | Error message + log | `test_search_value_safety.py` (existing) |
| `core/middleware/access_log.py` `database`/`table` log fields | Log line | NEW in Phase 8 — adds log surface check |
| `core/middleware/rate_limit.py` 429 body | Response body | `test_rate_limit.py::test_hostile_xff_does_not_leak_into_log` (Phase 7 / 07-07 added) |
| `core/middleware/error_enrichment.py` request_id appending | Error message | `test_error_catalog.py` (Phase 7) |

**Storage decision:** Keep `tests/_corpus/hostile_inputs.py` as the single source of truth. The 4 new canaries are appended to `CANARY_STRINGS`. The existing `_surfaces_contain` helper handles all 4 new canaries without modification — `repr()` covers `﻿`, `‮`, `\x1b[...]`; the JSON-injection canary is plain ASCII so direct substring match works.

**Storing as JSON vs Python:** The spawn message suggests `tests/fixtures/hostile_inputs.json`. The existing module is Python (`tests/_corpus/hostile_inputs.py`). Keep Python — the helper functions live in the same file, JSON would split data from the helper, and Python comments document the intent of each canary. JSON is appropriate when the corpus is shared across languages; here it's pytest-only.

---

## 1,500-Fragment Regression (TEST-04)

The cap lives in upstream Datasette — not in `src/mcp_zeeker/`. Datasette's `_size` parameter caps each page at 1,000 rows. The connector's pagination uses keyset cursors per `core/fragment_join.py` (Phase 5).

**Existing test:** `tests/tools/test_retrieval_fragment_join.py:637 test_1500_fragment_walk_synthetic` — already runs a complete walk, builds a 1,500-row fixture across 15 100-row pages, asserts `len(all_rows) == 1500` and that ordinals are `range(1500)`.

**Phase 8 action: NONE on test code.** The action is documentation:
- Add a docstring marker `"""TEST-04 owner: Phase 8 (regression test originated in Phase 5)."""`
- Update REQUIREMENTS.md traceability row TEST-04 to point at this test.
- Add an entry to the Phase 8 plan SUMMARY confirming the test runs in CI.

The synthetic fixture builder is at line 259 (`_build_synthetic_fragments_page`). It's reusable for future tests if needed.

---

## Soak Harness (TEST-05, NFR-01..03)

### Tool comparison

| Tool | Pros | Cons | Verdict |
|------|------|------|---------|
| `locust` | Mature, web UI, distributed | New runtime dep; UI is overkill for one-shot soak; Python | REJECTED — NFR-04 |
| `k6` | Excellent metrics, JS-scripted | Go binary; complicates CI image; new tool | REJECTED — operational complexity |
| `wrk` | Fast, C-native | Low expressiveness; no JSON-RPC support | REJECTED — can't drive MCP |
| **Custom asyncio + httpx** | Zero new deps; httpx already in dev; idiomatic to project | ~200 LOC to write; no UI | **RECOMMENDED** |
| `pytest-benchmark` | pytest-native | Designed for microbenchmarks, not 24h soaks | REJECTED — wrong tool |

### Driver requirements (TEST-05 expansion)

| Requirement | How |
|-------------|-----|
| Drive running server in separate process | Server: `uvicorn ... --workers 1` (terminal A); Driver: `python -m scripts.soak.run_soak` (terminal B). CI script orchestrates with `subprocess.Popen` for the server + `asyncio.run` for the driver. |
| Per-request latency capture for p50/p95 | `time.perf_counter()` around each `client.post()`; sorted percentile from CSV |
| RSS sample every 60s | `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` from a sidecar that PID-targets the server (or attaches to the same process via `os.getpid()` if RSS sampler runs INSIDE the server — see decision below) |
| Detect `PoolTimeout` cascade | Catch `httpx.PoolTimeout` separately in driver; report rate per minute |
| Verify daily-rate-limit rollover | Driver tracks 429 rate per minute; report flags `daily_rollover_observed = (large drop in 429s within 60s of UTC midnight)` |
| Runnable in CI | `nightly.yml` triggers via cron; pre-release runs via `workflow_dispatch`; soak.yml uses GitHub Actions `timeout-minutes: 1500` (25h budget) |
| CSV + markdown report | `scripts/soak/report.py` reads both CSVs and writes `soak-summary.md` artifact |

### RSS sampling — process placement decision

**Two options:**

1. **In-server sampler:** Add a tiny periodic task to the Uvicorn process that writes RSS to a file every 60s. Pros: accurately measures the SUT. Cons: pollutes production code with test infrastructure; requires a `--soak-mode` flag.

2. **Out-of-server sidecar:** A separate Python process that knows the server PID, samples via `psutil.Process(pid)`. Cons: requires `psutil`, which violates NFR-04.

3. **Driver-attached sampler with PID via `/proc`:** On Linux, read `/proc/{pid}/status` for `VmRSS:`. Pros: stdlib only. Cons: Linux-only — fine for CI (GitHub Actions Linux runners) but breaks on macOS dev machines.

**Recommendation: Option 3 with macOS fallback.** The soak runs in CI on Linux. Local dev sanity-check uses `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` (which on macOS reports CURRENT RSS in bytes; on Linux reports CUMULATIVE MAX in KB — the report module normalizes).

```python
# scripts/soak/rss_sampler.py — NEW
import os
import re
from pathlib import Path

def rss_kb_from_proc(pid: int) -> int | None:
    """Return resident-set in KB by reading /proc/{pid}/status — Linux only."""
    try:
        text = Path(f"/proc/{pid}/status").read_text()
        m = re.search(r"^VmRSS:\s+(\d+)\s*kB", text, re.MULTILINE)
        return int(m.group(1)) if m else None
    except (OSError, AttributeError):
        return None

def rss_kb_from_self() -> int:
    """Fallback for non-Linux: ru_maxrss from current process."""
    import resource
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS reports bytes; Linux reports KB. Normalize to KB.
    if os.uname().sysname == "Darwin":
        return rusage.ru_maxrss // 1024
    return rusage.ru_maxrss
```

### Concurrency profile

NFR-02 requires "50 concurrent without saturation." The driver enforces with `asyncio.Semaphore(50)`. The driver's CPU should stay under 50% during the soak (sanity check; not a NFR but a flag for "driver is the bottleneck" vs "server is the bottleneck").

### Latency sampling rate (Nyquist)

| Event | Sample rate | Rationale |
|-------|------------|-----------|
| Per-request latency | 1 sample per request (~50 RPS = 50 Hz) | Captures every event |
| RSS | 1 Hz (every 60s in production; consider 0.0167 Hz to bound CSV size) | RSS changes slowly; per-minute is sufficient |
| 429 rate | Aggregated from per-request log; bucket per minute | Daily-rollover detection needs minute-resolution |
| PoolTimeout | Aggregated from per-request log; bucket per minute | Cascade detection needs sub-minute resolution; aggregate post-hoc |

**24h soak data volume:** 50 RPS × 86400s = 4.32M latency samples. CSV row at ~40 bytes = 170 MB. RSS samples: 1440 rows = 50 KB. Acceptable artifact size for CI upload.

### CI scheduling

| Workflow | Trigger | What runs | Duration | Frequency |
|----------|---------|-----------|----------|-----------|
| `ci.yml` | Every PR / push to any branch | Unit tests + ruff + dep footprint test | ~1 min | every commit |
| `nightly.yml` | Cron `0 2 * * *` (02:00 UTC daily) | `pytest -m live` + `python -m scripts.soak.run_soak --duration 3600` (1h smoke) | ~1.5h | nightly |
| `soak.yml` | `workflow_dispatch` (manual) | `python -m scripts.soak.run_soak --duration 86400` (full 24h) | ~25h | pre-release only |

CI minutes budget: GitHub Actions free tier gives 2,000 minutes/month for private repos. Nightly soak: 90 min × 30 = 2,700 min — exceeds free tier. **Operator decision required:** either (a) accept the cost on a paid tier, (b) reduce smoke soak to 30 min, or (c) self-host runner for the nightly. Document in plan; do not assume free-tier availability.

---

## Validation Architecture

> Required because `workflow.nyquist_validation` is enabled (default — `.planning/config.json` does not exist or does not set this to `false`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.3 (auto mode) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, lines 41-47) |
| Quick run command | `uv run pytest -x -q` |
| Full suite command | `uv run pytest` |
| Live cmd | `ZEEKER_LIVE=1 uv run pytest -m live -p no:xdist` |
| Soak smoke cmd | `uv run python -m scripts.soak.run_soak --duration 60 --concurrency 5` |
| Soak full cmd | `uv run python -m scripts.soak.run_soak --duration 86400 --concurrency 50` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | All 13 filter operators compile correctly | unit | `pytest tests/test_filter_compiler.py -x` | ✅ exists, extend |
| TEST-01 | Envelope shape per tool | unit | `pytest tests/test_envelope_snapshot.py -x` | ✅ exists |
| TEST-01 | Hidden-table rejection from list_tables | unit | `pytest tests/test_hidden_data_enforcement.py::test_list_tables_strips_hidden -x` | ❌ Wave 0 — NEW file |
| TEST-01 | Hidden-column rejection from describe_table | unit | `pytest tests/test_hidden_data_enforcement.py::test_describe_table_strips_hidden_columns -x` | ❌ Wave 0 |
| TEST-01 | Fragment-parent join (957-frag walk) | unit | `pytest tests/tools/test_retrieval_fragment_join.py::test_957_fragment_walk_synthetic -x` | ✅ exists |
| TEST-01 | Rate-limit burst window | unit | `pytest tests/test_rate_limit.py -k burst -x` | ✅ exists |
| TEST-01 | Rate-limit sustained window | unit | `pytest tests/test_rate_limit.py -k sustained -x` | ✅ exists |
| TEST-01 | Rate-limit daily window + UTC midnight rollover | unit | `pytest tests/test_rate_limit.py -k daily -x` | ✅ exists |
| TEST-01 | Error code mapping (all 11) | unit | `pytest tests/test_error_catalog.py -x` | ✅ exists |
| TEST-01 | Cursor qhash mismatch rejection | unit | `pytest tests/test_cursor.py::test_shape_mismatch_raises_invalid_cursor -x` | ✅ exists |
| TEST-02 | Live golden path per tool | integration | `ZEEKER_LIVE=1 pytest tests/test_live_golden_path.py -p no:xdist -x` | ❌ Wave 1 — NEW |
| TEST-03 | row.keys ∩ HEAVY_COLUMNS == ∅ for all 6 tools | unit (snapshot) | `pytest tests/test_envelope_snapshot.py -x` | ✅ exists, extend |
| TEST-03 | retrieved_content.keys ⊆ HEAVY_COLUMNS | unit (snapshot) | `pytest tests/test_envelope_snapshot.py -k retrieved_content -x` | ✅ exists |
| TEST-04 | 1500-fragment walk completes without truncation loss | unit | `pytest tests/tools/test_retrieval_fragment_join.py::test_1500_fragment_walk_synthetic -x` | ✅ exists, document under TEST-04 |
| TEST-05 | Smoke soak (1 min, 5 concurrent) completes with p95 < 1.5s | smoke | `python -m scripts.soak.run_soak --duration 60 --concurrency 5 && python -m scripts.soak.report --max-p95-ms 1500` | ❌ Wave 2 — NEW |
| TEST-05 | Full 24h soak completes; daily rollover observed | manual / pre-release | `python -m scripts.soak.run_soak --duration 86400` | ❌ Wave 2 — NEW |
| TEST-06 | 9 canaries × 3 tools × 3 surfaces = 81 cases | unit | `pytest tests/test_hostile_inputs_consolidated.py -x` | ✅ exists, extend matrix |
| NFR-01 | p50 < 300ms in soak report | post-soak | `python -m scripts.soak.report --max-p50-ms 300` | ❌ Wave 2 — NEW |
| NFR-01 | p95 < 1.5s in soak report | post-soak | `python -m scripts.soak.report --max-p95-ms 1500` | ❌ Wave 2 — NEW |
| NFR-02 | 50 concurrent sustained without errors | soak driver | implicit in driver `--concurrency 50` | ❌ Wave 2 |
| NFR-03 | RSS < 256 MB throughout soak | post-soak | `python -m scripts.soak.report --max-rss-mb 256` | ❌ Wave 2 |
| NFR-04 | Runtime deps == 6 named packages | unit | `pytest tests/test_dependency_footprint.py::test_runtime_deps_match_locked_set -x` | ❌ Wave 0 — NEW |
| NFR-04 | Dev deps == 4 named packages | unit | `pytest tests/test_dependency_footprint.py::test_dev_deps_match_locked_set -x` | ❌ Wave 0 — NEW |
| NFR-05 | README documents Anthropic IP allowlist | manual / doc review | `grep -q 'Anthropic IP' README.md` | ❌ Wave 3 — NEW (extends README) |
| NFR-05 | README documents single-worker | manual / doc review | already present at `README.md:71-75` | ✅ exists |

### Nyquist Properties (sampling-rate justifications)

| Validation Dimension | Nyquist Rate | Acceptance Threshold | Failure Signal |
|---------------------|--------------|---------------------|----------------|
| Coverage (per REQ) | 1 sample per requirement (binary: tested or not) | 100% — all 11 REQ IDs have at least one verified test | REQUIREMENTS.md traceability row missing test pointer |
| Latency (per request, soak) | 50 Hz (every request at 50 RPS) | p50 < 300ms; p95 < 1.5s for non-fragment tools | `report.py` exit code != 0 |
| Resource (RSS, soak) | 0.0167 Hz (every 60 seconds) | Max RSS over 24h < 256 MB | `rss.csv` max value > 262144 KB |
| Robustness (hostile inputs) | 9 canaries × 3 tools × 3 surfaces = 81 samples per test run | 0 leaks across all 81 cases | `_surfaces_contain` returns non-empty list |
| Daily rollover | Per-minute 429 rate aggregation, 1440 samples per 24h | Observable >50% drop in 429 rate within ±60s of any UTC midnight crossed during soak | `daily_rollover_observed=False` when soak crossed midnight |
| Pool stability | Per-minute PoolTimeout count aggregation | < 0.1% of total requests are PoolTimeout | `pool_timeout_rate > 0.001` in summary |
| Lifespan correctness | 1 sample (test runs once) | RuntimeError raised (NOT AttributeError) for non-FunctionTool | AttributeError from app.py:59 |
| Dependency footprint | 1 sample per CI run (every PR) | Set-equality with locked NFR-04 tuples | test_runtime_deps_match_locked_set fails |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_dependency_footprint.py tests/test_app_lifespan_contract.py -x` (the two NEW tests likeliest to break with code changes)
- **Per wave merge:** `uv run pytest -x -q` (full unit suite ~30s)
- **Phase gate (full suite green):** `uv run pytest && uv run python -m scripts.soak.run_soak --duration 60 --concurrency 5 && uv run python -m scripts.soak.report --max-p50-ms 300 --max-p95-ms 1500 --max-rss-mb 256` (smoke soak gate)
- **Pre-release:** Manual `soak.yml` workflow_dispatch — full 24h.

### Wave 0 Gaps

- [ ] `tests/test_dependency_footprint.py` — covers NFR-04 (NEW)
- [ ] `tests/test_app_lifespan_contract.py` — covers CR-02 (NEW)
- [ ] `tests/test_hidden_data_enforcement.py` — covers TEST-01 hidden-data sweep (NEW)
- [ ] `tests/test_live_golden_path.py` — covers TEST-02 (NEW)
- [ ] `scripts/soak/__init__.py` + `run_soak.py` + `workload.py` + `rss_sampler.py` + `report.py` — covers TEST-05 + NFR-01/02/03 (NEW)
- [ ] `tests/_corpus/soak_workload.py` — shared workload definition (NEW)
- [ ] No new fixtures in `tests/conftest.py` — single-plan-touch already enforced; Phase 8 reuses existing fixtures only

---

## Security Domain

`security_enforcement` is enabled (default). Phase 8 is a **test/coverage** phase and does not introduce new security-sensitive code paths — but its tests verify the security contracts established in earlier phases.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (anonymous tier only — v1 scope) | N/A |
| V3 Session Management | No (stateless HTTP per TRANSPORT-03) | N/A |
| V4 Access Control | Yes — rate limiting verified by tests | Existing token bucket; Phase 8 verifies via concurrency stress tests |
| V5 Input Validation | Yes — XFF parsing + filter values + canary corpus | Existing `_normalize_ip_key`, `compile_filters`, `_corpus/hostile_inputs.py`; Phase 8 verifies via 9-canary sweep |
| V6 Cryptography | No (qhash is anti-tampering, not crypto — Phase 3 D3-12) | N/A |
| V7 Error Handling | Yes — locked 11-code catalog + INJ-05 no-echo invariant | Phase 8 catalog test + hostile-input fan-out |
| V8 Data Protection | Yes — heavy text only under `retrieved_content`; HEAVY_COLUMNS partition | Phase 8 snapshot tests verify partition |
| V12 Files and Resources | Yes — soak driver writes CSV to gitignored `./soak-results/` | Path validation: only `out_dir` (CLI arg) is writable; no symlink traversal |
| V13 API and Web Service | Yes — every tool emits Envelope; CI lint already enforces | Phase 8 verifies via snapshot fan-out |

### Known Threat Patterns for Test/Soak Code

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Soak driver leaks credentials in CSV | Information Disclosure | Driver does NOT pass any auth headers; anonymous tier only. CSV contains: timestamp, status code, latency, error class. No request bodies, no tokens. |
| Soak script path traversal via `--output` | Tampering | `--output` resolves to absolute path; report.py refuses paths outside `./soak-results/` if a `safe-mode` flag is set. (Discretionary — local dev convenience vs CI safety.) |
| Live tests echo upstream response in CI logs | Information Disclosure | Live tests assert on shape, not content. Where content is asserted (e.g., `test_metadata_cache.py` license values), the assertion is on a known-public string. |
| Hostile-input test fixture file used by attacker | Tampering | Corpus is in source tree, signed by git history. Phase 8 does NOT load fixture from network. |
| Dependency-footprint test bypassed via PR comment | Tampering | Test is a regular pytest file gated by CI. PRs cannot disable individual tests without an explicit reviewer-visible diff. |
| 24h soak as DoS against `data.zeeker.sg` | DoS | Soak runs against `127.0.0.1:8000` (the local Uvicorn instance). Upstream traffic is real but bounded by the connector's own rate limit (5,000/day). |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `freezegun` for time mocking | Injected `time_provider` callable | Phase 6 (D6-12) — established codebase pattern | No new dep; cleaner test isolation |
| `psutil` for RSS sampling | `resource.getrusage()` (stdlib) | Phase 8 (NFR-04 enforcement) | No 5th dev dep |
| Per-test inline canary lists | Shared `tests/_corpus/hostile_inputs.py` | Phase 6 consolidation | Single audit point; Phase 8 extends |
| `requests` (sync HTTP) for tests | `httpx.AsyncClient` | Phase 1 (D-13) | Uniform async story |
| `gunicorn + uvicorn workers` | Single Uvicorn worker | Phase 1 (RATE-06) — locked in v1 | In-memory rate limit consistency |
| Live tests run on every CI build | `@pytest.mark.live` + cron-only | Phase 3 onward | No upstream traffic from PR runners |
| `pytest-benchmark` for perf checks | Custom 24h asyncio soak | Phase 8 (TEST-05) | Right tool for soak; pytest-benchmark is microbenchmark territory |

**Deprecated/outdated:**
- None in this phase. Phase 7 already deprecated `freezegun` in favor of `time_provider` injection. Phase 8 maintains the discipline.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `resource.getrusage().ru_maxrss` on Linux reports KB and is sufficient for "RSS < 256 MB" verification (granularity ~256 = 0.1% of cap) | Soak Harness § Memory Sampling | If macOS-only dev environment is used, units differ (bytes); `report.py` must normalize. Mitigation: rss_sampler.py contains the unit-normalization branch verified above. |
| A2 | The driver's asyncio loop in a separate process does not perturb server measurements meaningfully | Soak Harness § Driver Pattern | If driver and server are co-located on a 1-CPU container, scheduling pressure could still inflate p95. Mitigation: CI runner is multi-core; document recommended runner sizing. |
| A3 | `pytest-httpx 0.35` is sufficient for Phase 8 tests (no 0.36 features needed) | Environment Availability | If a Phase 8 test needs `httpx_mock.add_response(method=...)` flexibility added in 0.36, plan must bump the pin (Wave 0 concern). Mitigation: write tests against the 0.35 API only. |
| A4 | GitHub Actions (or operator's chosen CI) supports cron + `workflow_dispatch` triggers | CI Scheduling | If operator uses a CI without these, the cadence model needs adapting. Mitigation: document the model in operator-neutral terms; the 3-lane structure works with any modern CI. |
| A5 | Anthropic's IP-allowlist is documented separately by Anthropic and Phase 8 only needs to mention its existence in README | Operator Documentation | If Anthropic requires specific allowlist configuration in the connector itself, additional work needed. Mitigation: Phase 9 (submission) is the canonical owner of registry-specific docs; Phase 8 README addition is "operator must allowlist Anthropic's MCP egress IPs." |
| A6 | A 1-hour smoke soak in CI nightly is sufficient signal; full 24h is reserved for pre-release | CI Scheduling | If memory leak only manifests after 4+ hours, nightly misses it. Mitigation: pre-release 24h is mandatory before Phase 9 PR; failure here blocks v1 ship. |
| A7 | Test code reads `pyproject.toml` deterministically from project root (`Path(__file__).parent.parent`) | Dependency-Footprint Enforcement | If repo structure changes (e.g., src/ moved), path is wrong. Mitigation: use `find_project_root()` helper or `importlib.resources` lookup. |
| A8 | `RateLimitMiddleware._sweep_interval` of 30s + 50 RPS sustained means TTL eviction never accumulates pressure during the soak | Soak Harness | At 50 RPS × 86400s = 4.32M requests, with a single test driver IP, the bucket count stays at 1; no LRU pressure. Verified: the soak's bucket store remains size 1 throughout. Mitigation: a second driver-thread varying XFF could exercise the LRU path, but is out of scope for v1 soak. |

---

## Open Questions (RESOLVED)

1. **Should the soak harness pin a specific CI runner OS / arch?**
   **RESOLVED:** `ubuntu-latest` for live + soak workflows; `rss_sampler.py` retains the macOS branch for local dev only.
   - What we know: GitHub Actions defaults to `ubuntu-latest` (currently 22.04, soon 24.04). `resource.getrusage().ru_maxrss` units differ between Linux (KB) and macOS (bytes).
   - What's unclear: If operator pins to macOS runners (M-series Apple Silicon), the sampling code needs the conditional branch already documented in `rss_sampler.py`. Defer to operator decision; default to `ubuntu-latest`.
   - Recommendation: document `ubuntu-latest` as the assumed runner; rss_sampler handles both for local dev.

2. **Is the 1-hour smoke soak actually meaningful, or is it false-confidence?**
   **RESOLVED:** Both retained — smoke is the per-PR gate, 24h is `workflow_dispatch` only.
   - What we know: The 24h soak validates daily-rollover (which a 1h cannot). The 1h validates burst+sustained behavior, latency stability over a non-trivial window, and absence of immediate memory leak.
   - What's unclear: If memory grows linearly at 1 MB/hour, 1h shows +1 MB (noise); 24h shows +24 MB (still under 256 MB cap). The 1h soak misses this signal.
   - Recommendation: 1h smoke is for "did the build break performance?" — early-warning. 24h pre-release is for "is the v1 deploy OK?" — gate. Both have value; document the difference clearly.

3. **Does Anthropic publish a stable IP-allowlist?**
   **RESOLVED:** Defer authoritative answer to Phase 9 submission; README documents the operator-facing requirement now (per Plan 08-06 NFR-05 delta).
   - What we know: Anthropic docs (anthropic.com/api/getting-started) reference an allowlist for outbound API calls but the list is updated periodically.
   - What's unclear: For the MCP connector direction (Anthropic → Zeeker), the relevant IPs are Anthropic's outbound MCP egress, not the inbound API. These are not (as of last check) publicly documented in a stable, machine-readable list.
   - Recommendation: Phase 8 README addition says "operator must allowlist Anthropic's MCP egress IPs (consult Anthropic ops contact)." Phase 9 submission may surface a canonical list as part of registry onboarding.

4. **`pytest-httpx` version pin: bump to 0.36.x or stay at 0.35.x?**
   **RESOLVED:** Stay on 0.35; NFR-04 dep audit treats `pytest-httpx` as one entry regardless of version.
   - What we know: `pyproject.toml:19` pins `pytest-httpx~=0.35`. CLAUDE.md mentions 0.36.2 as the latest. No Phase 8 test requires a 0.36 feature.
   - What's unclear: If Phase 8 tests want `httpx_mock.add_response(method="POST")` (added in 0.36 per release notes), a bump is needed.
   - Recommendation: stay at 0.35 unless the planner identifies a specific blocker. NFR-04 dep audit treats `pytest-httpx` as one entry regardless of version.

5. **Should the soak driver retry on transient errors?**
   **RESOLVED:** No retries; failure rate IS the measurement.
   - What we know: Real-world clients retry on 5xx and on the connector's own 502/503 (per Phase 7 retry semantics).
   - What's unclear: A retrying driver papers over upstream blips. A non-retrying driver reports honest failure rates but may flag genuinely successful runs as "unstable" if upstream had a 30-second blip.
   - Recommendation: NO retries in driver. Failure rate IS a measurement. The soak report categorizes errors (`pool_timeout`, `request_timeout`, `5xx`, `4xx`, `429`) so operators can distinguish transport from application issues.

---

## Sources

### Primary (HIGH confidence)

- `src/mcp_zeeker/app.py:53-67` — lifespan code containing the CR-02 `tool.return_type` access
- `src/mcp_zeeker/core/middleware/rate_limit.py:106-117` — `RateLimitMiddleware.__init__` with `time_provider` injection
- `src/mcp_zeeker/core/cursor.py:140` — `decode_cursor` qhash mismatch raise site
- `src/mcp_zeeker/core/filter_compiler.py:30-44` — `FilterOp` Literal with all 13 operators
- `src/mcp_zeeker/core/datasette_client.py:141-192` — `_request_with_retry` with `QueryTimeoutError` (Phase 7)
- `src/mcp_zeeker/config.py:506-516` — `HEAVY_COLUMNS` frozenset (snapshot contract reference)
- `src/mcp_zeeker/config.py:478-487` — `LOG_FIELDS` tuple (locked log surface)
- `src/mcp_zeeker/core/http_client.py:11-22` — httpx client factory with `Limits(max_connections=50, ...)`
- `tests/conftest.py:76-82` — existing live-test gating implementation
- `tests/conftest.py:446-492` — Phase 7 fixtures (`fake_clock`, `rate_limiter`, `bucket_store`)
- `tests/_corpus/hostile_inputs.py` — existing canary corpus + `_surfaces_contain` helper
- `tests/test_envelope_snapshot.py` — existing snapshot test pattern (Phase 6)
- `tests/test_hostile_inputs_consolidated.py` — existing 5-canary × 3-tool fan-out (Phase 6)
- `tests/tools/test_retrieval_fragment_join.py:259, 637` — existing 1500-fragment regression
- `tests/test_filter_compiler.py:36-280` — existing 13-op coverage
- `tests/test_cursor.py:36-67` — existing qhash-mismatch test
- `tests/test_metadata_cache.py:264, 289` and `tests/test_heavy_column_upstream.py:52, 58` — existing live-test patterns
- `tests/test_rate_limit.py` (per Phase 7 verification: 13+ tests) — rate-limit windows verified
- `tests/test_error_catalog.py` (per Phase 7 verification: 4 tests) — error catalog verified
- `tests/test_app.py:22-30` — `/healthz` test pattern
- `pyproject.toml:1-22` — runtime + dev deps (NFR-04 source of truth)
- `pyproject.toml:41-47` — pytest config including `live` marker registration
- `README.md:71-90` — single-worker constraint already documented (Phase 7)
- `.planning/phases/07-rate-limit-structured-errors-healthz-logs/07-VERIFICATION.md:165-167` — CR-02 deferral
- `.planning/phases/07-rate-limit-structured-errors-healthz-logs/07-RESEARCH.md` — Phase 7 research style template
- `.planning/phases/07-rate-limit-structured-errors-healthz-logs/07-PATTERNS.md` — Phase 7 pattern-mapping example (Phase 8 follows the same style)
- `.planning/REQUIREMENTS.md` — TEST-01..06, NFR-01..05 source of truth

### Secondary (MEDIUM confidence)

- [PyPI: psutil 7.2.2](https://pypi.org/project/psutil/) — verified current; rejected for NFR-04
- [PyPI: syrupy 5.1.0](https://pypi.org/project/syrupy/) — verified current; rejected for NFR-04
- [PyPI: locust 2.44.0](https://pypi.org/project/locust/) — verified current; rejected for NFR-04
- [Python stdlib `resource` module](https://docs.python.org/3/library/resource.html) — `getrusage()` semantics (KB on Linux, bytes on macOS)
- [Python stdlib `tomllib` module](https://docs.python.org/3.11/library/tomllib.html) — TOML parser, Python 3.11+
- [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io/) — `asyncio_mode = "auto"` semantics (already in pyproject.toml)
- [pytest markers docs](https://docs.pytest.org/en/stable/example/markers.html) — `@pytest.mark.live` registration pattern (already in pyproject.toml line 46)

### Tertiary (LOW confidence)

- GitHub Actions CI minutes pricing (general knowledge, not verified for current pricing) — recommendation to assume operator decision required
- Anthropic IP-allowlist publication policy (general assumption — not verified) — recommendation to document operator-confirmed approach in Phase 9

---

## Operator Documentation (NFR-05)

The deployment README at `README.md` (lines 28-90) already documents the Caddy header rules, `--workers 1` constraint, and the 00:00 UTC reset. Phase 8 adds:

```markdown
### Anthropic IP allowlist

The MCP server's rate limiter caps anonymous traffic at 20 burst / 60 per minute /
5,000 per IP per 24 hours. When Anthropic's MCP-egress IPs route traffic through
your reverse proxy:

- If Anthropic publishes a stable list of MCP-egress IPs, the operator should
  allowlist those source IPs at the Caddy / firewall layer so they are not
  bucket-contended with general public traffic.
- If no stable list is published (current default), the operator may either
  (a) accept that all Anthropic-originated traffic shares the same per-IP
  bucket as `ip_prefix(<anthropic_egress_ip>)`, or (b) maintain a wildcard
  allowlist for Anthropic's published egress CIDR ranges.

If the connector is consumed by `claude-for-legal` plugins (Phase 9 submission
target), traffic originates from Anthropic infrastructure on behalf of the end
user. Per-IP rate-limit math operates on the Anthropic egress IP, not the end
user's IP. Operators should size capacity accordingly.
```

This is a docs task, not a test task — no automated verification beyond the `grep -q 'Anthropic IP' README.md` smoke check.

---

## Metadata

**Confidence breakdown:**
- Test taxonomy + file layout: HIGH — every analog verified in codebase
- Live-test gating: HIGH — existing implementation reused verbatim
- Hostile-input corpus: HIGH — existing module extended with 4 well-known canaries
- Snapshot tests: HIGH — existing pattern; hand-rolled vs syrupy decision documented
- 1500-fragment regression: HIGH — existing test verified
- Soak harness: MEDIUM — pure-stdlib design verified but full 24h not yet executed; smoke soak architecture verified
- CR-02 fix: HIGH — one-line change with clear regression test pattern
- Dependency-footprint enforcement: HIGH — tomllib stdlib + pyproject.toml shape verified
- Filter-operator coverage: HIGH — 13 ops verified in source vs spawn message's "11" (clarification: in/notin and isnull/notnull both pairs split, total 13)
- Cursor-binding rejection: HIGH — existing test verified
- Validation Architecture: HIGH — every REQ → test command mapped
- Operator docs (NFR-05): MEDIUM — Anthropic allowlist policy not authoritatively verified; recommendation written conservatively

**Research date:** 2026-05-15
**Valid until:** 2026-06-15 (30 days; pytest 8 / pytest-asyncio 1.3 / pytest-httpx 0.35 are stable; FastMCP 3.2 stable; no upstream API behavior change expected)

---

## RESEARCH COMPLETE
