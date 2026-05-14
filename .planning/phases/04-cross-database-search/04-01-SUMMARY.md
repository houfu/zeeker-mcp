---
phase: 04-cross-database-search
plan: 01
subsystem: search-foundation
tags: [foundation, fts-escape, envelope-extension, wave-0-stubs, conftest-consolidation, phase4]
requires:
  - "src/mcp_zeeker/config.py (existing ALLOWED_DATABASES, HIDDEN_TABLES, LICENSE_MIXED, DEFAULT_ATTRIBUTION, TOOL_TRAILER, HEAVY_COLUMNS)"
  - "src/mcp_zeeker/core/envelope.py (existing Envelope, Provenance, Pagination, for_database_list / for_table_list / for_rows factories)"
  - "src/mcp_zeeker/core/visibility.py (existing 6 raise_unknown_* helpers + _visible_tables / _visible_columns / _resolve_table — Phase 3)"
  - "src/mcp_zeeker/core/datasette_client.py (existing DatasetteClient, _request_with_retry, get_database, get_table_rows, TableSummary, UpstreamCallFailed)"
  - "src/mcp_zeeker/core/cursor.py + filter_compiler.py (pure-function module shape — analog for fts_escape.py + search.py)"
  - "tests/conftest.py (existing _db_url / _table_url / _tables_payload / TABLE_ROWS_STUB / stub_upstream / stub_table_rows / bound_datasette_client fixtures)"
  - "tests/fixtures/datasette/search/*.json — 15 captured fixtures (research commit cb645bd)"
provides:
  - "config.SEARCH_DENYLIST_PATTERNS ((`_fragments`,) — D4-04)"
  - "config.SEARCH_PREVIEW_DEFAULTS (4 ordered candidate tuples per preview field — D4-12)"
  - "config.SEARCH_PREVIEW_OVERRIDES ({} in v1 — D4-12 / D4-22)"
  - "core.envelope.Pagination — extended with upstream_total_hits (dict[str,int] default {}) and failed_tables (int default 0) — D4-17"
  - "core.envelope.Envelope.for_search_results(rows, upstream_total_hits, failed_tables) — multi-DB factory mirroring for_database_list (D4-16)"
  - "core.visibility.raise_invalid_query() — 7th sole-emission helper, fixed-literal `invalid_query: query syntax not supported` (D4-09 / INJ-05)"
  - "core.datasette_client.TableSummary.fts_table (str | None = None) — LOAD-BEARING safety gate (04-RESEARCH §3.1 / Pitfall 3)"
  - "core.datasette_client.UpstreamCallFailed.status (int | None = None) — surfaces HTTP status for orchestrator all-tables-400 detection (04-RESEARCH §3.7)"
  - "core.fts_escape.escape_fts5(query) — pure FTS5 phrase-wrap (D4-08, SEARCH-06)"
  - "core.search.resolve_preview_columns(db, table, available) — pure helper resolving the 4 preview fields with heavy-column filter (D4-12)"
  - "core.search.searchable_tables_for(db) — SKELETON (NotImplementedError; Plan 04-02 body-fills with FOUR-gate filter per D4-02)"
  - "core.search.fan_out_search(escaped, target_tables, per_table_limit) — SKELETON (NotImplementedError; Plan 04-02 body-fills with anyio + zip_longest per D4-05/D4-06)"
  - "tests/conftest.py: _load_search_fixture(filename) + _SEARCH_FIXTURE_DIR + SEARCH_ROWS_STUB + extended _tables_payload(names, *, fts_tables=None, columns=None)"
  - "tests/test_fts_escape.py: 14 GREEN tests (13 corpus + 1 purity check)"
  - "tests/test_resolve_preview_columns.py: 5 GREEN tests covering all resolution branches"
  - "tests/test_search_value_safety.py: 5-canary parametrized RED stub (skipped until Plan 04-02)"
  - "tests/tools/test_search.py: 7 handler-level RED stubs"
  - "tests/tools/test_search_auto_discovery.py: 4 auto-discovery RED stubs"
  - "tests/tools/test_search_errors.py: 7 error-path RED stubs"
  - "tests/tools/test_search_side_channel.py: 2 counter-patch RED stubs"
  - "tests/core/__init__.py + tests/core/test_fan_out_search.py: 5 orchestrator RED stubs"
affects:
  - "Phase 1/2/3 tests/tools (verified unchanged — 190 passed)"
  - "Existing _tables_payload callers (backward-compat preserved via default-None kwargs)"
tech-stack:
  added: []
  patterns:
    - "Locked-catalog discipline carried into Phase 4: only one new error code `invalid_query`; PRD §12 catalog stays at 6 retrieval codes + 1 search code"
    - "Single-call-site security boundary: core/fts_escape.py owns FTS5 phrase wrap; core/search.py owns preview resolution + orchestrator"
    - "Sole-emission helper for invalid_query (7th raise_* helper in core/visibility.py — fixed-literal message per INJ-05)"
    - "LOAD-BEARING upstream metadata gate: TableSummary.fts_table is not None decides search dispatch (Pitfall 3 — Datasette silently ignores _search= on non-FTS tables)"
    - "Defense-in-depth heavy-column filter: resolve_preview_columns rejects HEAVY_COLUMNS even when an override / default candidate names them (D3-04 / D4-12)"
    - "Function-body imports in Wave 0 stub tests so collection succeeds before the module-under-test exists (Phase 2 idiom preserved)"
    - "pytest.skip BEFORE fixture-consuming body to avoid pytest-httpx teardown errors on unused stub responses (NEW Phase 4 refinement)"
    - "EXPLICIT ORDERED add_response for transient-failure tests (Phase 2 LEARNING — NO is_reusable=True for retry-path tests)"
    - "Stub `fan_out_search` returns 4-tuple matching Plan 04-02 final shape (plan-checker LOW issue resolution — zero second-edit churn for Wave 2)"
key-files:
  created:
    - "src/mcp_zeeker/core/fts_escape.py"
    - "src/mcp_zeeker/core/search.py"
    - "tests/test_fts_escape.py"
    - "tests/test_resolve_preview_columns.py"
    - "tests/test_search_value_safety.py"
    - "tests/tools/test_search.py"
    - "tests/tools/test_search_auto_discovery.py"
    - "tests/tools/test_search_errors.py"
    - "tests/tools/test_search_side_channel.py"
    - "tests/core/__init__.py"
    - "tests/core/test_fan_out_search.py"
  modified:
    - "src/mcp_zeeker/config.py"
    - "src/mcp_zeeker/core/envelope.py"
    - "src/mcp_zeeker/core/visibility.py"
    - "src/mcp_zeeker/core/datasette_client.py"
    - "tests/conftest.py"
decisions:
  - "fan_out_search stub signature returns a 4-tuple `(merged_rows, upstream_total_hits, failed_tables, failure_statuses)` instead of the 3-tuple originally listed in Plan 04-01 task description. This matches Plan 04-02's binding (planner-checker LOW issue resolution) and avoids a second-edit churn in Wave 2 when the orchestrator body needs the per-failure status list to drive the all-tables-400 detection."
  - "Wave 0 stub tests use `pytest.skip(...)` BEFORE consuming the `bound_datasette_client` / `bound_metadata_cache` fixtures so pytest-httpx teardown does not fail on unused pre-registered upstream responses. The skipped tests still collect cleanly. Plan 04-02 removes the skip lines and stubs the actual upstream responses."
  - "Conftest.py extensions ALL consolidated into this plan — Plans 04-02 / 04-03 / 04-04 MUST NOT EDIT tests/conftest.py (Phase 2/3 cross-plan conftest merge-conflict LEARNING carried forward)."
  - "Pre-existing ruff E501 errors in config.py (TABLE_DESCRIPTIONS / LIGHT_COLUMNS docstring values, 12 errors total) are out of scope for Plan 04-01 — logged to deferred-items.md. Plan 04-01 keeps its config.py diff to +30 lines of Phase 4 additions only; running `ruff format` introduced unrelated whitespace reflows in pre-existing dict alignments which were reverted."
metrics:
  duration_min: ~10
  completed_date: 2026-05-14
  tasks: 3
  commits: 3
  files_created: 11
  files_modified: 5
  tests_added: 33 (14 GREEN + 30 RED stubs + 5 in test_resolve_preview_columns — see Tests Added below)
---

# Phase 4 Plan 1: Foundation — Source Edits, Pure Helpers, Wave 0 Stubs Summary

**One-liner:** Lays the Phase 4 cross-DB search foundation — four backward-compatible source-edit fragments (`config.py` Phase 4 globals + `Pagination` extension + `for_search_results` factory + `raise_invalid_query` helper + `TableSummary.fts_table` + `UpstreamCallFailed.status`) plus the pure-helper modules (`escape_fts5` pure FTS5 phrase-wrap, `resolve_preview_columns` pure preview-shape resolver) plus the `core/search.py` orchestrator skeleton plus the consolidated `conftest.py` extension plus the 6 Wave 0 stub test files — all proven against the contract corpora from 04-RESEARCH §3.6 / §3.7 / §3.8 / Pitfall 1 / Pitfall 3 / Pitfall 5.

## What shipped

### Task 1 — Four source-edit fragments (commit `0901598`)

#### `src/mcp_zeeker/config.py` (D4-02 / D4-04 / D4-12 / D4-22)

Three new globals appended after `HEAVY_COLUMNS` (lines 280-308):

```python
SEARCH_DENYLIST_PATTERNS: tuple[str, ...] = ("_fragments",)
SEARCH_PREVIEW_DEFAULTS: dict[str, tuple[str, ...]] = {
    "title":   ("title", "case_name", "name", "heading"),
    "date":    ("decision_date", "published_date", "pub_date", "date"),
    "summary": ("summary", "description", "abstract", "section"),
    "url":     ("source_url", "decision_url", "source_link", "link",
                "item_url", "url", "permalink"),
}
SEARCH_PREVIEW_OVERRIDES: dict[str, dict[str, str | None]] = {}
```

04-RESEARCH §3.8 audit confirmed all 12 currently-searchable tables resolve cleanly via defaults; `SEARCH_PREVIEW_OVERRIDES` stays empty in v1.

#### `src/mcp_zeeker/core/envelope.py` (D4-16 / D4-17)

`Pagination` extended with two new fields (defaults preserve backward compat — Pydantic 2 deep-copies the mutable `{}` default per-instance):

```python
upstream_total_hits: dict[str, int] = {}
failed_tables: int = 0
```

New factory `Envelope.for_search_results(rows, upstream_total_hits, failed_tables=0)` mirrors `for_database_list`'s multi-DB provenance shape (`database=None`, `table=None`, `license=config.LICENSE_MIXED`, `attribution=config.DEFAULT_ATTRIBUTION`) and instantiates `Pagination` with the two new fields populated.

#### `src/mcp_zeeker/core/visibility.py` (D4-09 / SEARCH-06 / INJ-05)

Added `raise_invalid_query() -> NoReturn` as the 7th sole-emission helper. Body:

```python
raise ToolError("invalid_query: query syntax not supported")
```

The message is a FIXED literal — never echoes the query string. Docstring documents the three trigger paths: (a) empty/whitespace query (D4-19 step 1 handler guard), (b) limit out-of-range (D4-11 belt-and-suspenders), (c) all-tables-400 fan-out fallback (D4-09 case c).

#### `src/mcp_zeeker/core/datasette_client.py` (04-RESEARCH §3.1 / §3.7)

Two minimal corrections folded into Plan 04-01 per the RESEARCH-flagged gaps:

1. `TableSummary.fts_table: str | None = None` — the LOAD-BEARING safety gate. Plan 04-02's `searchable_tables_for` uses `fts_table is not None` to decide search dispatch; without this gate, pdpc.enforcement_decisions would surface rowid-ordered rows as fake "search results" (Pitfall 3 / T-04-04).
2. `UpstreamCallFailed.__init__(message, *, status=None)` + `_request_with_retry` passes `status=resp.status_code` to the 504 and catch-all raise sites. Plan 04-02's handler reads `.status` to detect all-tables-400 and map to `invalid_query` per D4-09 case c.

Both edits backward-compatible: existing fixtures load with `fts_table=None`; existing `UpstreamCallFailed("msg")` raise sites (transport-error, retry-exhausted) keep `status=None` via default.

### Task 2 — Pure helpers (commit `4e9429d`)

#### `src/mcp_zeeker/core/fts_escape.py` (D4-08, SEARCH-06)

One pure stdlib function — single line body, ToolError-free, NEVER raises:

```python
def escape_fts5(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'
```

The empty-string case (`""` → `'""'`) is the handler's responsibility (D4-19 step 1 fires `raise_invalid_query()` BEFORE escape).

#### `src/mcp_zeeker/core/search.py` (D4-02 / D4-05 / D4-12 / D4-18 skeleton)

Three functions:

1. `resolve_preview_columns(db, table, available)` — CONCRETE pure helper implementing D4-12. SOLE call-site for `SEARCH_PREVIEW_DEFAULTS` / `SEARCH_PREVIEW_OVERRIDES`. Heavy columns filtered at resolution time so an override naming a heavy column can never smuggle it into the preview shape. Returns `None` drop signal when title or url cannot be resolved.

2. `searchable_tables_for(db)` — SKELETON, raises `NotImplementedError("Plan 04-02 ships searchable_tables_for body — D4-02 (FOUR-gate filter)")`. Docstring documents the FOUR-gate filter contract.

3. `fan_out_search(escaped, target_tables, per_table_limit)` — SKELETON, raises `NotImplementedError`. Returns a 4-tuple `(merged_rows, upstream_total_hits, failed_tables, failure_statuses)` — matches Plan 04-02's final binding so Wave 2 doesn't have to re-edit the signature.

Full import block (`anyio`, `structlog`, `fastmcp.exceptions.ToolError`, `mcp_zeeker.config`, `DatasetteClient`, `UpstreamCallFailed`, `_visible_columns`, `_visible_tables`) + `log = structlog.get_logger()` already in place — Plan 04-02 body-fills WITHOUT touching imports.

### Task 3 — Tests + conftest extension (commit `8199207`)

#### `tests/conftest.py` extensions

- `_load_search_fixture(filename)` module-level helper + `_SEARCH_FIXTURE_DIR` constant (reads `tests/fixtures/datasette/search/<filename>` via `Path + json.loads`).
- Extended `_tables_payload(names, *, fts_tables=None, columns=None)` — backward-compatible with all Phase 1/2/3 callers (190 passed unchanged).
- `SEARCH_ROWS_STUB` module-level constant — minimal Datasette `_search=` response shape with preview-resolvable columns.

**Consolidation rule (D4-22 / CONTEXT.md line 538):** ALL Phase 4 conftest edits are in this plan. Plans 04-02 / 04-03 / 04-04 MUST NOT EDIT `tests/conftest.py`.

#### 14 GREEN tests (pure-helpers)

- `tests/test_fts_escape.py`: 13 parametrized inputs covering the 04-RESEARCH §3.6 contract corpus (Section 5(a), `he said "hi"`, "OR AND NEAR", "NEAR", "*", ":column:value", "((((", "NEAR/5 word", trailing backslash, "", "   ", 5 KB payload, "text:foo OR id:0") + 1 defensive purity test (`test_escape_fts5_is_pure_string`) that imports the module source as text and asserts `raise ` / `await ` never appear after the docstring.
- `tests/test_resolve_preview_columns.py`: 5 tests covering all D4-12 resolution branches per 04-RESEARCH §3.8 — defaults_resolve_judgments, about_singapore_law_no_date_returns_null, missing_url_returns_none_drop_signal, override_suppresses_field, heavy_column_never_selected.

#### 30 RED Wave 0 stub tests (collect cleanly, skip pending Plan 04-02)

- `tests/test_search_value_safety.py`: 5-canary parametrized hostile-input corpus (`</system>`, `NEAR('data' 'protection') AND NOT`, `"x"*5001`, `ZEEKER_CANARY_42`, `"\udc80"`). `_surfaces_contain` helper lifted from Phase 3 — Plan 04-02 reuses without rewrite.
- `tests/tools/test_search.py`: 7 handler-level tests (happy paths, preview shape, no heavy cols, envelope provenance, upstream_total_hits, no-/-/search.json dispatch, limit=1). Local `datasette_client` fixture + `_table_url_re` regex matcher both paste-verified from `tests/tools/test_query_table.py`.
- `tests/tools/test_search_auto_discovery.py`: 4 tests (fts_table gate, _fragments denylist, pdpc-no-dispatch — the load-bearing T-04-04 test, no-preview-columns drop).
- `tests/tools/test_search_errors.py`: 7 tests (empty/whitespace/limit-OOR → invalid_query; unknown_database; all-400 → invalid_query per 04-RESEARCH §3.7; all-500 → upstream_unavailable). Phase 2 LEARNING annotated (NO `is_reusable=True` for retry-path tests).
- `tests/tools/test_search_side_channel.py`: 2 counter-patch tests (sole-emission code-path identity for `raise_invalid_query`; structured-log emission for `search_table_no_preview_columns`).
- `tests/core/test_fan_out_search.py` (+ `tests/core/__init__.py`): 5 orchestrator tests (round-robin merge, exhausted-table skip, partial failure, all-fail, upstream_total_hits aggregation).

Wave 0 discipline: each test uses `pytest.skip("RED until Plan 04-02 ...")` BEFORE any fixture-consuming body so pytest-httpx teardown does not fail on unused stub responses. Plan 04-02 removes the skip lines and stubs the actual upstream responses.

## D-IDs implemented

| D-ID | Decision | Where it lands |
|------|----------|----------------|
| D4-02 | Per-DB auto-discovery via TableSummary.fts_table + visible + denylist + preview-resolvable | `config.SEARCH_DENYLIST_PATTERNS` + `core.datasette_client.TableSummary.fts_table` + `core.search.searchable_tables_for` skeleton |
| D4-04 | Denylist suffix `_fragments` | `config.SEARCH_DENYLIST_PATTERNS = ("_fragments",)` |
| D4-08 | FTS5 phrase-wrap escape | `core.fts_escape.escape_fts5` |
| D4-09 | Locked error catalog adds `invalid_query` (fixed literal) | `core.visibility.raise_invalid_query` |
| D4-12 | Preview-column resolver with defaults + overrides + heavy filter | `config.SEARCH_PREVIEW_DEFAULTS` + `SEARCH_PREVIEW_OVERRIDES` + `core.search.resolve_preview_columns` |
| D4-16 | `Envelope.for_search_results` factory (multi-DB scope) | `core.envelope.Envelope.for_search_results` |
| D4-17 | Pagination extension: `upstream_total_hits` + `failed_tables` | `core.envelope.Pagination` |
| D4-18 | Orchestrator skeleton (Plan 04-02 body) | `core.search.searchable_tables_for` + `fan_out_search` skeletons |
| D4-22 | Override pattern + conftest consolidation | `SEARCH_PREVIEW_OVERRIDES = {}` + consolidated `tests/conftest.py` extensions |

## 04-RESEARCH corrections folded in

| § | Correction | Edit location |
|---|-----------|---------------|
| §3.1 / Pitfall 1 / Pitfall 3 | `TableSummary` missing `fts_table` field | `core/datasette_client.py` — added `fts_table: str \| None = None` |
| §3.7 / Pitfall 5 | `UpstreamCallFailed` has no HTTP status attribute | `core/datasette_client.py` — added `__init__(message, *, status=None)` + raise sites pass `status=resp.status_code` |
| §3.8 | 12-table preview audit drove `SEARCH_PREVIEW_DEFAULTS` tuples | `config.py` — exact ordered tuples cover all 12 searchable tables |

(The auto-discovery source correction RESEARCH-§3.2 is Plan 04-02's territory — 04-01 ships only the data-model changes.)

## Files for Plan 04-02 to consume

### Public API in `core/search.py`
- `resolve_preview_columns(db: str, table: str, available: set[str]) -> dict[str, str | None] | None` — CONCRETE, GREEN.
- `searchable_tables_for(db: str) -> tuple[str, ...]` — SKELETON. Plan 04-02 fills body with the FOUR-gate filter (`fts_table is not None` → visible → not-denylist → preview-resolvable). Docstring already lists the algorithm.
- `fan_out_search(escaped_query: str, target_tables: list[tuple[str, str, dict[str, str | None]]], per_table_limit: int) -> tuple[list[dict], dict[str, int], int, list[int | None]]` — SKELETON. Plan 04-02 fills body with `anyio.create_task_group()` + `anyio.move_on_after(0.8)` + per-table `_one_table` task + `_round_robin_merge` via `itertools.zip_longest`. Imports already in place.

### Public API in `core/fts_escape.py`
- `escape_fts5(query: str) -> str` — pure, ToolError-free, GREEN.

### Public API in `core/envelope.py`
- `Envelope.for_search_results(*, rows, upstream_total_hits, failed_tables=0) -> Envelope` — multi-DB factory. Plan 04-02's handler calls this with the orchestrator's return tuple.
- `Pagination` — new fields `upstream_total_hits` and `failed_tables` available.

### Public API in `core/visibility.py`
- `raise_invalid_query() -> NoReturn` — sole-emission helper. Plan 04-02's handler imports as `from mcp_zeeker.core.visibility import raise_invalid_query` (function-body counter-patches in `test_search_side_channel.py` target `mcp_zeeker.tools.search.raise_invalid_query`).

### Public API in `core/datasette_client.py`
- `TableSummary.fts_table: str | None = None` — `searchable_tables_for` reads.
- `UpstreamCallFailed.status: int | None = None` — `fan_out_search` reads via per-failure exception inspection; handler maps all-400 → `invalid_query`.

### Test infrastructure in `tests/conftest.py`
- `_load_search_fixture(filename)` — Plan 04-02 / 04-03 use to replay captured fixtures.
- `SEARCH_ROWS_STUB` — minimal preview-resolvable shape for stub_table_rows fixture.
- `_tables_payload(names, *, fts_tables, columns)` — Plan 04-02 calls with kwargs to populate fts_table + columns per-table.

## Test files left RED (by design — Plan 04-02 turns GREEN)

- `tests/test_search_value_safety.py` (5 parametrized cases)
- `tests/tools/test_search.py` (7 tests)
- `tests/tools/test_search_auto_discovery.py` (4 tests)
- `tests/tools/test_search_errors.py` (7 tests)
- `tests/tools/test_search_side_channel.py` (2 tests)
- `tests/core/test_fan_out_search.py` (5 tests)

Total: 30 RED stubs. All collect cleanly; all use `pytest.skip("RED until Plan 04-02 ...")` to stay out of the failure count.

## Conftest.py status

**TOUCHED IN PLAN 04-01 ONLY** — Plans 04-02 / 04-03 / 04-04 MUST NOT EDIT `tests/conftest.py`. (Phase 2 / Phase 3 cross-plan conftest merge-conflict LEARNING carried forward — see `02-LEARNINGS.md` / `03-LEARNINGS.md`.)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] fan_out_search stub signature evolved to 4-tuple**
- **Found during:** Task 2 (designing the skeleton)
- **Issue:** Plan 04-01 task description listed the return as a 3-tuple `(merged_rows, upstream_total_hits, failed_tables)`. Plan 04-02 needs a 4th element `failure_statuses: list[int | None]` to drive the all-tables-400 → invalid_query mapping (04-RESEARCH §3.7 / D4-09 case c).
- **Fix:** Plan 04-01's stub already returns the 4-tuple. The plan-checker LOW issue note in the executor prompt called this out explicitly — using the final 4-tuple shape avoids a second-edit churn in Wave 2.
- **Files modified:** `src/mcp_zeeker/core/search.py` (skeleton + docstring), `tests/core/test_fan_out_search.py` (test docstrings reference `failure_statuses`)
- **Commit:** `4e9429d` / `8199207`

**2. [Rule 3 - Blocking] Wave 0 stub tests use `pytest.skip` BEFORE consuming fixtures**
- **Found during:** Task 3 (initial test run)
- **Issue:** First version of `test_search_value_safety.py` consumed `bound_datasette_client` + `bound_metadata_cache` fixtures, which pre-register stub upstream responses. When the test body raised `NotImplementedError` from the stub handler, no upstream requests were issued — pytest-httpx teardown then asserted on unused responses, producing 5 ERROR (not skip).
- **Fix:** Move `pytest.skip(...)` BEFORE any fixture-consuming body. The stub test signature in Plan 04-01 takes only `canary` and `pytest.skip()` fires immediately at function entry. Plan 04-02 adds the fixtures + removes the skip line.
- **Files modified:** `tests/test_search_value_safety.py`
- **Commit:** `8199207`

**3. [Rule 3 - Blocking] FTS5 phrase-wrap docstring example contained accidental triple-quote**
- **Found during:** Task 2 (first pytest run)
- **Issue:** The original docstring example `escape_fts5('he said "hi"') -> '"he said ""hi"""'` contained `"""` (three quotes in a row from the doubled-quote example) that prematurely closed the module docstring, breaking `tests/test_fts_escape.py` collection with `SyntaxError`.
- **Fix:** Replaced the explicit example outputs in the docstring with prose descriptions ("Section 5(a) wrapped in double quotes", "doubled internal quotes inside wrap"). The actual examples remain in the parametrized test file `tests/test_fts_escape.py` for full coverage.
- **Files modified:** `src/mcp_zeeker/core/fts_escape.py`
- **Commit:** `4e9429d`

### Out of Scope (logged to `deferred-items.md`)

**Pre-existing ruff E501 errors in `src/mcp_zeeker/config.py`** — 12 line-too-long errors in `TABLE_DESCRIPTIONS` / `LIGHT_COLUMNS` docstring values (lines 113-145 — well before my Phase 4 additions at line 280+). Verified by stashing Plan 04-01 edits and re-running ruff against HEAD. Out of scope for this plan; logged to `.planning/phases/04-cross-database-search/deferred-items.md` with suggested fix (`# noqa: E501` or wrap in a future chore PR).

## Verification

### Inline assertions (verbatim from plan)

```bash
$ uv run python -c "..." (Task 1 inline verify — 8 properties asserted)
OK

$ uv run python -c "..." (Task 2 inline verify — search module + fts_escape)
OK

$ uv run python -c "..." (Task 3 inline verify — conftest backward compat)
OK
backward compat OK
```

### Test counts

- **GREEN pure-helper tests:** `pytest tests/test_fts_escape.py tests/test_resolve_preview_columns.py -x -q` → **19 passed in 0.01s** (14 escape corpus inputs + 5 resolve_preview_columns).
- **Wave 0 stub collection:** `pytest tests/tools/test_search.py tests/tools/test_search_auto_discovery.py tests/tools/test_search_errors.py tests/tools/test_search_side_channel.py tests/core/test_fan_out_search.py tests/test_search_value_safety.py --collect-only -q` → **30 tests collected in 0.01s**.
- **Wave 0 stub run:** all 30 SKIPPED (RED until Plan 04-02 — clean runner).
- **Phase 1/2/3 regression:** `pytest tests/ --ignore=tests/manual` → **190 passed, 32 skipped, 0 failed** (32 = 30 Wave 0 + 2 pre-existing skip markers).

### INJ-05 grep

```bash
$ grep -rE "(f\"|f')[^\"']*\{(query|search)" src/mcp_zeeker/core/visibility.py src/mcp_zeeker/core/fts_escape.py src/mcp_zeeker/core/search.py
# (empty — no f-string interpolation of user query/search content)
```

### Ruff

- `ruff check src/mcp_zeeker/core/envelope.py src/mcp_zeeker/core/visibility.py src/mcp_zeeker/core/datasette_client.py src/mcp_zeeker/core/fts_escape.py src/mcp_zeeker/core/search.py tests/conftest.py tests/test_fts_escape.py tests/test_resolve_preview_columns.py tests/test_search_value_safety.py tests/tools/test_search.py tests/tools/test_search_auto_discovery.py tests/tools/test_search_errors.py tests/tools/test_search_side_channel.py tests/core/test_fan_out_search.py` → **All checks passed.**
- `ruff check src/mcp_zeeker/config.py` → 12 pre-existing E501 errors (deferred per above).

## Self-Check: PASSED

- `src/mcp_zeeker/config.py`: FOUND (3 Phase 4 globals appended).
- `src/mcp_zeeker/core/envelope.py`: FOUND (Pagination extension + for_search_results).
- `src/mcp_zeeker/core/visibility.py`: FOUND (raise_invalid_query helper).
- `src/mcp_zeeker/core/datasette_client.py`: FOUND (TableSummary.fts_table + UpstreamCallFailed.status).
- `src/mcp_zeeker/core/fts_escape.py`: FOUND (escape_fts5).
- `src/mcp_zeeker/core/search.py`: FOUND (resolve_preview_columns concrete; 2 skeleton helpers).
- `tests/conftest.py`: FOUND (_load_search_fixture + SEARCH_ROWS_STUB + extended _tables_payload).
- `tests/test_fts_escape.py` + `tests/test_resolve_preview_columns.py`: FOUND (19 GREEN tests).
- 6 Wave 0 stub test files + `tests/core/__init__.py`: FOUND.
- Commit `0901598` (Task 1): FOUND in `git log --oneline`.
- Commit `4e9429d` (Task 2): FOUND.
- Commit `8199207` (Task 3): FOUND.
