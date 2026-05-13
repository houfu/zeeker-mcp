---
phase: 02
plan: 01
subsystem: discovery-infrastructure
tags:
  - mcp
  - datasette
  - cache
  - config
dependency_graph:
  requires:
    - 01-skeleton-transport-first-tool
  provides:
    - MetadataCache singleton+contextvar
    - config_lookup.hidden_columns_for helper
    - config.py Phase 2 denylists
    - DatasetteClient.get_table_column_types
    - Wave-0 test stubs
  affects:
    - src/mcp_zeeker/app.py
    - tests/conftest.py
tech_stack:
  added: []
  patterns:
    - singleton+contextvar dual-binding (mirrors DatasetteClient F-2 fix)
    - anyio.Lock single-flight refresh
    - normalize-at-ingest DB key lowercase (D2-05)
    - stale-on-error cache (D2-03)
key_files:
  created:
    - src/mcp_zeeker/core/metadata_cache.py
    - src/mcp_zeeker/core/config_lookup.py
    - tests/test_metadata_cache.py
    - tests/test_hidden_columns_lookup.py
    - tests/tools/test_list_tables.py
    - tests/tools/test_describe_table.py
    - tests/tools/test_discovery_side_channel.py
  modified:
    - src/mcp_zeeker/config.py
    - src/mcp_zeeker/core/datasette_client.py
    - src/mcp_zeeker/app.py
    - tests/conftest.py
    - tests/test_config.py
decisions:
  - "D2-05: DB-name normalization at ingest only in _fetch_and_normalize; zero .lower() in public lookup methods"
  - "D2-03: stale-on-error pattern — _last_fetch not updated on refresh failure so next call retries"
  - "Pitfall 3: anyio.Lock() constructed inside __init__ (not module level)"
  - "F-2: bind() sets both _singleton AND contextvar — production cross-task reads hit singleton"
  - "Rule 3 deviation: minimal metadata_cache.py stub created in Task 1 to unblock conftest.py import"
  - "test_stale_on_error: explicit 3-response sequence fixture instead of is_reusable + add_response ordering"
metrics:
  duration_seconds: 507
  completed_date: "2026-05-13"
  tasks_completed: 3
  tests_before: 36
  tests_after: 58
  tests_skipped: 4
---

# Phase 2 Plan 01: Foundation Infrastructure (Config + MetadataCache + DatasetteClient) Summary

**One-liner:** MetadataCache with anyio.Lock single-flight, stale-on-error, and D2-05 normalize-at-ingest; config.py Phase 2 denylists populated; DatasetteClient extended; Wave-0 test stubs created.

## What Was Built

### config.py Extensions (9 new/changed keys)

| Key | Change | Line |
|-----|--------|------|
| `HIDDEN_TABLES` | Extended to all 4 DBs with `_zeeker_schemas`/`_zeeker_updates` (D2-09) | ~40 |
| `HIDDEN_COLUMNS` | Type changed to `dict[str, set[str]]`; populated with global + 3 per-table entries (D2-10) | ~50 |
| `URL_COLUMNS` | Type changed to `dict[str, str]`; 13 entries | ~56 |
| `FRAGMENT_PARENTS` | Type changed to `dict[str, dict]`; 3 entries with parent_table/fk/pk/order_by | ~69 |
| `LIGHT_COLUMNS` | Type changed to `dict[str, list[str]]`; 14 entries (D2-11) | ~83 |
| `TABLE_DESCRIPTIONS` | NEW: fallback table descriptions for pdpc/zeeker-judgements/sglawwatch | ~130 |
| `COLUMN_DESCRIPTIONS` | NEW: fallback column descriptions for pdpc.enforcement_decisions | ~148 |
| `COLUMN_TYPES` | NEW: fallback column types for two fragment tables lacking _zeeker_schemas rows | ~163 |
| `METADATA_TTL_SECONDS` | NEW: reads `METADATA_TTL_SECONDS` env var, default 1800 (D2-04) | ~192 |

### MetadataCache (`src/mcp_zeeker/core/metadata_cache.py`)

Public API:
- `current()` — returns contextvar-bound instance or singleton, raises RuntimeError if neither
- `bind(cache)` — sets both `_singleton` AND contextvar (F-2 cross-task fix)
- `reset(token)` — restores contextvar only (singleton persists)
- `clear_singleton()` — test teardown seam
- `get_table_metadata(database, table)` — direct dict lookup on normalized store (D2-05)
- `get_column_description(database, table, column)` — navigates table metadata columns dict
- `get_database_license(database)` — direct dict lookup (D2-05)
- `force_refresh()` — sets `_last_fetch=0.0` and awaits `_ensure_fresh()`

D2-05 enforcement: `.lower()` appears ONLY inside `_fetch_and_normalize`. Zero `.lower()` calls in the four public lookup methods (verified by acceptance criterion grep).

### config_lookup.py (`src/mcp_zeeker/core/config_lookup.py`)

- `hidden_columns_for(database, table)` — ONLY call-site for `config.HIDDEN_COLUMNS`
- Returns `global_set | per_table_set` union

### DatasetteClient Extensions (`src/mcp_zeeker/core/datasette_client.py`)

- `TableSummary` extended with `hidden: bool = False`, `count: int | None = None`, `columns: list[str] = []`, `primary_keys: list[str] = []`
- `extra="ignore"` preserved — Phase 1 fixtures with name-only payloads still work
- `get_table_column_types(database)` — fetches `/_zeeker_schemas.json`, parses `column_definitions` JSON, returns `{table_name: {col_name: sql_type}}`; falls back to `{}` on `UpstreamCallFailed`

### app.py Lifespan Extension

MetadataCache bound before DatasetteClient; reset in reverse order:
```python
mc = MetadataCache(http_client, config.UPSTREAM_URL, ttl=config.METADATA_TTL_SECONDS)
mc_token = MetadataCache.bind(mc)
token = DatasetteClient.bind(DatasetteClient(http_client))
# ...
finally:
    DatasetteClient.reset(token)
    MetadataCache.reset(mc_token)
```

### Test Infrastructure

- `tests/conftest.py`: `bound_metadata_cache` fixture + `pytest_collection_modifyitems` live-skip hook + richer `stub_upstream` payloads (hidden/count/columns)
- `tests/test_metadata_cache.py`: 8 passing tests + 1 live (auto-skipped)
- `tests/test_hidden_columns_lookup.py`: 3 passing tests
- 3 Wave-0 stubs: each has one `@pytest.mark.skip` test with function-body import (no module-level import)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Minimal metadata_cache.py stub created in Task 1**
- **Found during:** Task 1 conftest.py edit
- **Issue:** `tests/conftest.py` imports `from mcp_zeeker.core.metadata_cache import MetadataCache`, but `metadata_cache.py` is a Task 2 artifact. Without the file, all pytest runs would fail with `ImportError` when conftest is loaded.
- **Fix:** Created minimal stub with just the `MetadataCache` class skeleton (current/bind/reset/clear_singleton) to unblock Task 1 verification. Task 2 replaced it with the full implementation.
- **Files modified:** `src/mcp_zeeker/core/metadata_cache.py` (Task 1), then replaced (Task 2)
- **Commit:** a5b6dbe → 6d05fb7

**2. [Rule 1 - Bug] test_hidden_tables_initial updated to test_hidden_tables_phase2**
- **Found during:** Task 1 config.py edit
- **Issue:** Existing test `test_hidden_tables_initial` asserted `HIDDEN_TABLES["sglawwatch"] == {"metadata", "schema_versions"}` and others are empty. After Phase 2, all 4 DBs have platform-internal tables and `sglawwatch` has 4 entries.
- **Fix:** Updated test to verify D2-09 values: all DBs have `_zeeker_schemas`/`_zeeker_updates`; sglawwatch also has `metadata`/`schema_versions`.
- **Files modified:** `tests/test_config.py`
- **Commit:** a5b6dbe

**3. [Rule 1 - Bug] test_stale_on_error fixture redesigned for pytest-httpx ordering**
- **Found during:** Task 2 test verification
- **Issue:** Using `is_reusable=True` stub + `add_response(503)` later caused `_assert_options()` to fail at teardown because pytest-httpx returns the `is_reusable` 200 for every request (including the one intended to hit 503), leaving the 503 unconsumed.
- **Fix:** Created `stale_on_error_cache` fixture with explicit 3-response sequence (200, 503, 200) without `is_reusable`, matching the exact call count.
- **Files modified:** `tests/test_metadata_cache.py`
- **Commit:** 6d05fb7

## Test Counts

| Metric | Before | After |
|--------|--------|-------|
| Tests passing | 36 | 58 |
| Tests skipped | 0 | 4 (3 Wave-0 stubs + 1 live) |
| Tests failing | 0 | 0 |

## Threat Surface Scan

No new network endpoints introduced in this plan. `MetadataCache._fetch_and_normalize` consumes `/-/metadata.json` from the trusted upstream Datasette (already in the threat model as T-02-01/T-02-02). No new trust boundaries created. `config_lookup.py` reads in-process config constants only. `get_table_column_types` fetches `/_zeeker_schemas.json` (same upstream, same trust boundary as existing `get_database`).

## Self-Check: PASSED

Files verified present:
- `src/mcp_zeeker/core/metadata_cache.py` ✓
- `src/mcp_zeeker/core/config_lookup.py` ✓
- `tests/test_metadata_cache.py` ✓
- `tests/test_hidden_columns_lookup.py` ✓
- `tests/tools/test_list_tables.py` ✓
- `tests/tools/test_describe_table.py` ✓
- `tests/tools/test_discovery_side_channel.py` ✓

Commits verified:
- a5b6dbe — Task 1: config + conftest + Wave-0 stubs
- 6d05fb7 — Task 2: MetadataCache + config_lookup + unit tests
- 476be1a — Task 3: DatasetteClient extensions + app.py lifespan

Full test suite: 58 passed, 4 skipped, 0 failures.
