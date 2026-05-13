---
phase: 03-structured-retrieval-url-keyed-fetch
fixed_at: 2026-05-14T00:00:00Z
review_path: .planning/phases/03-structured-retrieval-url-keyed-fetch/03-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-05-14
**Source review:** `.planning/phases/03-structured-retrieval-url-keyed-fetch/03-REVIEW.md`
**Iteration:** 1
**Scope:** `critical_warning` (CR-01 + WR-01..WR-06; IN-01..IN-04 out of scope)

**Summary:**
- Findings in scope: 7
- Fixed: 7
- Skipped: 0

All 7 fixes verified against `pytest` (171 passed, 2 skipped live-only) inside
the isolated review-fix worktree before each commit. Each commit is atomic per
finding (CR-01 ships together with its new regression test file).

## Fixed Issues

### CR-01: Direct read of `config.URL_COLUMNS` in `tools/discovery.py` violates D2-10 / D3-04 single-source-of-truth

**Files modified:** `src/mcp_zeeker/tools/discovery.py`, `tests/test_config_lookup_single_source.py` (new)
**Commit:** `6744e98`
**Applied fix:** Replaced the direct `f"{database}.{table}" in config.URL_COLUMNS`
read in `describe_table` with `url_column_for(database, table) is not None`. Added
`url_column_for` to the `core.config_lookup` import line. Created a new test file
`tests/test_config_lookup_single_source.py` with two regression tests that walk
`src/mcp_zeeker/**/*.py` via Python AST (not regex — avoids docstring/comment
false positives) and assert that no module outside `core/config_lookup.py` reads
`config.URL_COLUMNS` or `config.HIDDEN_COLUMNS` as an attribute. The AST-based
implementation is stronger than the regex variant suggested in REVIEW.md because
it eliminates the false-positive on `visibility.py:71` (docstring mention) the
regex variant initially produced.

### WR-01: Silent float-to-int truncation in numeric filter coercion

**Files modified:** `src/mcp_zeeker/core/filter_compiler.py`, `tests/test_filter_compiler.py`
**Commit:** `3ff608e`
**Applied fix:** Added an explicit `isinstance(f.value, bool) or isinstance(f.value, float)`
check (bool first, because `isinstance(True, int)` is True) at the top of the
INTEGER coercion branch. Both cases raise the existing fixed-literal
`invalid_filter_op: value not coercible for operator` ToolError with `from None`
discipline. Added two regression tests
(`test_int_column_rejects_float_value`, `test_int_column_rejects_bool_value`)
covering all four numeric ops (gt/gte/lt/lte) and both bool values.

### WR-02: Limit-clamp error uses the wrong code from the locked catalog

**Files modified:** `src/mcp_zeeker/tools/retrieval.py`
**Commit:** `97f9700`
**Applied fix:** Per the explicit user-instruction guidance and REVIEW.md's
alternative recommendation: the PRD §12 catalog is LOCKED and extending it to
`invalid_limit` requires a planning re-loop (deferred to Phase 7 ERR-02). Kept
the existing `invalid_filter_op: limit must be between 1 and 200` message and
added an inline code comment justifying the overload — documenting that the
Pydantic Field(ge=1, le=200) gate is the dominant path in production and that
log/metrics consumers grepping on `invalid_filter_op:` should rely on the
message suffix `"limit must be between"` to disambiguate. No behavior change.

### WR-03: `LIGHT_COLUMNS` config drift can leak heavy columns at top level

**Files modified:** `src/mcp_zeeker/tools/retrieval.py`
**Commit:** `aa6c5c0`
**Applied fix:** Added `and c not in config.HEAVY_COLUMNS` to the list
comprehension in the `configured_light` branch of the default-projection path,
mirroring the existing subtraction in the fallback branch. No production
behavior change today (live config keeps LIGHT and HEAVY disjoint) — defensive
invariant enforcement against future config drift.

### WR-04: `raise_*` helpers declared `-> None` but never return (use `NoReturn`)

**Files modified:** `src/mcp_zeeker/core/visibility.py`
**Commit:** `8a5d7d5`
**Applied fix:** Added `from typing import NoReturn` and changed the return
annotation on all five sole-emission helpers (`raise_unknown_database`,
`raise_unknown_table`, `raise_unknown_column`,
`raise_unsupported_table_for_fetch`, `raise_not_found`) from `-> None` to
`-> NoReturn`. Type-checkers now correctly narrow values after each helper
call (e.g., `url_col` in `fetch()` is correctly seen as `str` after the
guard).

### WR-05: `canonical_shape_str` conflates `columns=[]` with `columns=None`

**Files modified:** `src/mcp_zeeker/core/cursor.py`, `tests/test_cursor.py`
**Commit:** `40bdc40`
**Applied fix:** Changed `sorted(columns) if columns else None` to
`sorted(columns) if columns is not None else None` so the truthiness coercion
no longer flattens `[]` into `None`. `sorted([])` returns `[]`, so the empty-list
path is preserved as documented. Added `test_columns_none_distinct_from_empty_list`
asserting the two shapes hash distinctly.

### WR-06: `get_table_column_types` does not defend against malformed upstream JSON

**Files modified:** `src/mcp_zeeker/core/datasette_client.py`
**Commit:** `e9a77c2`
**Applied fix:** Restructured the function so the entire upstream-call +
JSON-parsing path lives inside a single `try` block that catches
`(UpstreamCallFailed, KeyError, ValueError, IndexError, TypeError)` and maps
each to the documented empty-dict fallback. `json.JSONDecodeError` is a
subclass of `ValueError` and `.index()` misses raise `ValueError` too, so both
are covered by the listed exceptions without extra entries. Docstring updated
to match the broader fallback contract.

## Verification Summary

- **Per-finding verification:** every commit runs the relevant test module
  with `pytest -x` against the touched code path:
  - CR-01: `tests/test_config_lookup_single_source.py` (new) + `tests/tools/test_describe_table.py` → 13 passed
  - WR-01: `tests/test_filter_compiler.py` → 18 passed (incl. 2 new regression tests)
  - WR-02: `tests/tools/test_query_table.py` + `tests/tools/test_query_table_errors.py` → 39 passed
  - WR-03: `+ tests/tools/test_retrieval_side_channel.py` → 43 passed
  - WR-04: `tests/tools/test_retrieval_side_channel.py` + `test_query_table_errors.py` + `test_fetch.py` + `test_discovery_side_channel.py` → 27 passed
  - WR-05: `tests/test_cursor.py` + `tests/tools/test_query_table.py` → 35 passed (incl. 1 new regression test)
  - WR-06: `tests/test_datasette_client_retry.py` + `tests/tools/test_describe_table.py` + `tests/tools/test_query_table.py` → 42 passed
- **Final full-suite check:** `uv run pytest` reports `171 passed, 2 skipped, 5 warnings` (2 skipped are unrelated live-only `ZEEKER_LIVE=1` gated tests).

---

_Fixed: 2026-05-14_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
