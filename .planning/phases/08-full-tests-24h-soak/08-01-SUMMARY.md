---
phase: 08-full-tests-24h-soak
plan: "01"
subsystem: testing
tags: [pytest, tomllib, getattr, lifespan, NFR-04, CR-02, regression]

# Dependency graph
requires:
  - phase: 07-rate-limit-structured-errors-healthz-logs
    provides: app.py lifespan envelope-contract guard (CR-02 deferred from 07-VERIFICATION.md)
provides:
  - NFR-04 lock: tests/test_dependency_footprint.py asserts exact 6-runtime + 4-dev dep frozensets
  - CR-02 regression gate: tests/test_app_lifespan_contract.py ensures RuntimeError (not AttributeError) for non-FunctionTool
  - CR-02 production fix: src/mcp_zeeker/app.py:58 getattr() defensive read
affects: [08-02, 08-03, 08-04, 08-05, 08-06, phase-09-registry-submission]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "stdlib tomllib for pyproject.toml parsing in test assertions (Python 3.11+)"
    - "getattr(obj, attr, default) defensive attribute read for polymorphic FastMCP Tool subclasses"
    - "monkeypatch.setattr(mcp, 'list_tools', stub) for lifespan contract unit tests"

key-files:
  created:
    - tests/test_dependency_footprint.py
    - tests/test_app_lifespan_contract.py
  modified:
    - src/mcp_zeeker/app.py

key-decisions:
  - "Used re.split(r'[~=<>!;\\[\\s]', spec, maxsplit=1) to parse PEP 508 dep names — the loop-over-separators approach had an ordering bug: checking '=' before '>' returned 'starlette>' for 'starlette>=0.41,<2'"
  - "Pre-existing ruff errors in src/mcp_zeeker/config.py and several test files are out-of-scope; only plan-modified files (app.py, new test files) are ruff-clean"

patterns-established:
  - "Diff-readable NFR-04 assertion: f'added={actual - locked!r} removed={locked - actual!r}'"
  - "CR-02 monkeypatch pattern: SimpleNamespace without return_type attr + monkeypatch.setattr(mcp, 'list_tools', stub)"

requirements-completed:
  - NFR-04

# Metrics
duration: 4min
completed: 2026-05-15
---

# Phase 8 Plan 01: Wave 0 Foundation Summary

**NFR-04 dep-footprint lock (tomllib frozenset assertions) + CR-02 lifespan fix (getattr defensive read) — closes the Phase 7 deferred item end-to-end with a regression test**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-15T06:19:51Z
- **Completed:** 2026-05-15T06:23:36Z
- **Tasks:** 3 (Task 1: NFR-04 test, Task 2: CR-02 RED test, Task 3: CR-02 GREEN fix)
- **Files modified:** 3

## Accomplishments

- NFR-04 locked in CI: `test_dependency_footprint.py` asserts the exact 6-runtime + 4-dev frozensets using stdlib tomllib — any PR that silently adds/removes/renames a dep fails with a diff-readable message naming the exact delta.
- CR-02 closed end-to-end: `src/mcp_zeeker/app.py:58` changed from `tool.return_type` (raises `AttributeError` on non-FunctionTool) to `getattr(tool, "return_type", None)` (raises intended `RuntimeError("tool contract drift: ...")`).
- CR-02 regression gate: `test_app_lifespan_contract.py` ensures any future revert to direct-attribute access surfaces immediately in CI — it was RED before Task 3 and GREEN after.
- Full suite: 332 passed, 3 skipped — no regressions on existing tests.

## Task Commits

Each task was committed atomically:

1. **Task 1: NFR-04 dep-footprint test** - `aa19b87` (test)
2. **Task 2: CR-02 RED lifespan regression** - `002fb2a` (test)
3. **Task 3: CR-02 GREEN production fix** - `5ac31c9` (fix)

_Note: TDD tasks have separate RED (test) and GREEN (fix) commits._

## Files Created/Modified

- `tests/test_dependency_footprint.py` — NFR-04 lock: three plain (sync) tests asserting exact runtime + dev dep frozensets via stdlib tomllib; stdlib-only, no mcp_zeeker imports
- `tests/test_app_lifespan_contract.py` — CR-02 regression gate: one async test monkeypatching mcp.list_tools with a SimpleNamespace stand-in, asserting RuntimeError not AttributeError
- `src/mcp_zeeker/app.py` — Surgical one-line fix at line 58: `tool.return_type` → `getattr(tool, "return_type", None)`; TOOL_TRAILER guard and ImportError tolerance untouched

## Decisions Made

- **PEP 508 dep name parsing via regex**: Used `re.split(r"[~=<>!;\[\s]", spec, maxsplit=1)[0]` instead of the plan's loop-over-separators approach. The loop had a bug: checking `=` before `>` returned `"starlette>"` for `"starlette>=0.41,<2"` (the `=` in `>=` was found at index 9 before `>` at index 8). Regex split correctly splits at the first special character regardless of order. [Rule 1 - Bug fix during Task 1]
- **Pre-existing ruff errors out of scope**: `src/mcp_zeeker/config.py` and several test files have pre-existing E501/I001/F401 violations. Per deviation rule scope boundary, only the three plan-modified files are ruff-clean. Logged to note — not fixed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed PEP 508 dep-name parser ordering bug**
- **Found during:** Task 1 (running test_runtime_deps_match_locked_set)
- **Issue:** Loop-over-separators parsed `starlette>=0.41,<2` as `starlette>` because `=` appears at index 9 before `>` at index 8, so `=` was found first and `spec[:9]` was returned as `starlette>`
- **Fix:** Replaced loop with `re.split(r"[~=<>!;\[\s]", spec, maxsplit=1)[0]` — correctly splits at the first special character
- **Files modified:** tests/test_dependency_footprint.py
- **Verification:** `uv run pytest tests/test_dependency_footprint.py -x` exits 0; all 3 tests pass
- **Committed in:** aa19b87 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** Fix was necessary for correctness — wrong result meant the test would have incorrectly flagged `starlette>=0.41,<2` as an unknown dep. No scope creep.

## Issues Encountered

None beyond the parsing bug (auto-fixed above).

## NFR-04 Locked Frozensets

```python
RUNTIME_DEPS_LOCKED = frozenset({
    "fastmcp", "pydantic", "httpx", "starlette", "uvicorn", "structlog",
})
DEV_DEPS_LOCKED = frozenset({
    "pytest", "pytest-asyncio", "pytest-httpx", "ruff",
})
```

## CR-02 Exact Change

**Before (app.py line 58):**
```python
if tool.return_type is not Envelope:
```

**After (app.py line 58):**
```python
if getattr(tool, "return_type", None) is not Envelope:
```

## CR-02 Closure Smoke Confirmation

Running the canonical smoke from `08-01-PLAN.md <verification>` via `uv run python -c "..."`:

Output: `ok: tool contract drift: fake return_type is not Envelope`

The line starts with `ok:` (not `BAD:`). CR-02 is closed.

## conftest.py Unchanged

`git diff --name-only tests/conftest.py` — empty (no output). Per 08-RESEARCH.md "Wave 0 Requirements" line 88: single-plan-touch enforced.

## Known Stubs

None — all three files are fully implemented with no placeholder logic.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Next Phase Readiness

Wave 0 complete. The two regression gates are in place:
- `tests/test_dependency_footprint.py` — any dep drift fails CI immediately
- `tests/test_app_lifespan_contract.py` — any revert to direct attribute access fails CI immediately

**Forward pointer:** 08-02 / 08-03 / 08-04 / 08-05 may now run in parallel within their respective waves.

---
*Phase: 08-full-tests-24h-soak*
*Completed: 2026-05-15*
