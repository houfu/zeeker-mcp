---
phase: "08"
plan: "04"
subsystem: tests/ci
tags: [live-tests, ci, github-actions, test-cadence, TEST-02]
dependency_graph:
  requires:
    - "08-01"  # NFR-04 footprint lock + CR-02 fix must be in place
  provides:
    - "TEST-02 live golden-path cadence (nightly CI + shape-only assertions)"
  affects:
    - tests/test_live_golden_path.py
    - .github/workflows/live-tests.yml
tech_stack:
  added: []
  patterns:
    - "inline async fixture (bound_live_clients) — LIFO bind/reset of 4 singletons"
    - "shape-not-content live-test invariant — provenance.source + len(data) >= 1"
    - "GitHub Actions nightly cron + workflow_dispatch with pinned action versions"
key_files:
  created:
    - tests/test_live_golden_path.py
    - .github/workflows/live-tests.yml
  modified: []
decisions:
  - "Known-stable fetch URL sourced from tests/manual/PHASE3-CLIENT-VERIFY.md: https://www.elitigation.sg/gd/s/2026_SGDC_136 (zeeker-judgements.judgments) — present since Phase 3 UAT"
  - "fetch tool lives in src/mcp_zeeker/tools/retrieval.py (not tools/fetch.py) — plan interface doc was accurate; import path adjusted accordingly"
  - "assert len(envelope.data) == 4 for list_databases (stable since Phase 1); comment documents this catches a silent fifth DB appearing upstream"
  - "search test uses isinstance(envelope.data, list) as shape invariant; legitimate zero-hit result is valid per 08-PATTERNS.md"
metrics:
  duration: "~8 minutes"
  completed: "2026-05-15"
  tasks_completed: 2
  files_changed: 2
---

# Phase 8 Plan 04: Live Golden-Path Tests + Nightly CI Summary

**One-liner:** Six shape-only `@pytest.mark.live` tests (one per production tool) against `data.zeeker.sg`, automated nightly via `.github/workflows/live-tests.yml` — TEST-02 closed.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create tests/test_live_golden_path.py | fc8ed6d | tests/test_live_golden_path.py |
| 2 | Create .github/workflows/live-tests.yml | c27694d | .github/workflows/live-tests.yml |

## Verification Results

**Collection with ZEEKER_LIVE=1:**
```
ZEEKER_LIVE=1 uv run pytest tests/test_live_golden_path.py --collect-only -q
```
Collects exactly 6 tests:
- `tests/test_live_golden_path.py::test_live_list_databases`
- `tests/test_live_golden_path.py::test_live_list_tables`
- `tests/test_live_golden_path.py::test_live_describe_table`
- `tests/test_live_golden_path.py::test_live_search`
- `tests/test_live_golden_path.py::test_live_query_table`
- `tests/test_live_golden_path.py::test_live_fetch`

**Default pytest -x (no env var):**
```
uv run pytest tests/test_live_golden_path.py -x
```
Result: `6 skipped in 0.01s` — no failures, no errors. The conftest.py:76-83 hook auto-skips all live tests cleanly.

**Full unit suite:**
```
uv run pytest -x -q
```
Result: `370 passed, 13 skipped, 5 warnings` — no regressions.

**Ruff:** Both `ruff check` and `ruff format --check` exit 0 on `tests/test_live_golden_path.py`.

## Known-Stable fetch URL

The `test_live_fetch` test uses:

```
_STABLE_FETCH_URL = "https://www.elitigation.sg/gd/s/2026_SGDC_136"
```

Sourced from `tests/manual/PHASE3-CLIENT-VERIFY.md` (Phase 3 UAT scenario 4 — a published Singapore District Court judgment present since Phase 3 manual verification). Per threat T-FETCH-URL-DRIFT (accepted): if this URL ever 404s upstream, the test fails loudly with `not_found`; the operator updates `_STABLE_FETCH_URL` and re-runs.

## Live Cadence Verification (end-to-end)

The executor could NOT run `ZEEKER_LIVE=1 uv run pytest -m live -p no:xdist tests/test_live_golden_path.py -x` end-to-end against the real `https://data.zeeker.sg` from the dev machine at execution time (the worktree CI environment does not have outbound access to `data.zeeker.sg`). **Cadence verification is deferred to the first nightly CI run after this plan merges.** The test structure, binding choreography, and shape invariants are validated against the existing test suite patterns (analog: `tests/test_heavy_column_upstream.py:52-99`).

## Workflow File Properties (.github/workflows/live-tests.yml)

This is the **first `.github/` artifact** in the repository. Confirmed properties:

- Header comment references `08-RESEARCH.md "CI Scheduling" lines 1167-1175` with purpose (TEST-02) and trigger.
- `name: Live Tests`
- `on.schedule.cron: "0 2 * * *"` — 02:00 UTC nightly
- `on.workflow_dispatch:` — manual pre-release trigger
- `jobs.live.runs-on: ubuntu-latest`
- `jobs.live.timeout-minutes: 90`
- `actions/checkout@v4` — pinned major
- `astral-sh/setup-uv@v3` with `version: "0.11.14"` — CLAUDE.md pinned uv version
- `uv sync --frozen` — fails fast on uv.lock drift
- `ZEEKER_LIVE=1 uv run pytest -m live -p no:xdist` with `UPSTREAM_URL: https://data.zeeker.sg` env override

`find .github -type f` returns exactly one path: `.github/workflows/live-tests.yml`.

## tests/conftest.py NOT Modified

Confirmed: `git diff --name-only tests/conftest.py` is empty. The `bound_live_clients` async fixture is defined INLINE in `tests/test_live_golden_path.py` per the single-plan-touch discipline.

## Deviations from Plan

### Minor Discovery

**1. [Rule 1 - Info] fetch tool location**
- **Found during:** Task 1 implementation
- **Issue:** Plan interface docs stated `from mcp_zeeker.tools.fetch import fetch` — but there is no `tools/fetch.py` module. The `fetch` function lives in `src/mcp_zeeker/tools/retrieval.py`.
- **Fix:** Imported from `mcp_zeeker.tools.retrieval` instead. This is consistent with the actual codebase structure; the plan's interface reference was slightly inaccurate.
- **Files modified:** tests/test_live_golden_path.py (import path only)
- **Impact:** None — same function, correct module

## Threat Flags

No new threat surfaces introduced. The two files are test-only and CI-config — no new network endpoints, auth paths, or schema changes.

## Known Stubs

None. The test file has no stub values that would prevent plan objectives from being achieved.

## Forward Pointer

TEST-02 cadence in place; 08-05 (TEST-05 + NFR-01..03 soak harness) may proceed in parallel; 08-06 (NFR-05 README delta) follows in Wave 4.

## Self-Check: PASSED

- `tests/test_live_golden_path.py`: EXISTS (created, committed fc8ed6d)
- `.github/workflows/live-tests.yml`: EXISTS (created, committed c27694d)
- Commit fc8ed6d: FOUND in git log
- Commit c27694d: FOUND in git log
- 6 live tests collected under ZEEKER_LIVE=1: VERIFIED
- 6 tests skipped under default pytest: VERIFIED
- Full suite 370 passed: VERIFIED
- tests/conftest.py untouched: VERIFIED
