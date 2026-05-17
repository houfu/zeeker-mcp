---
phase: quick-260517-bki
plan: 01
subsystem: core/datasette_client
tags: [bugfix, error-mapping, regression-test, tdd]
requires: [QueryTimeoutError (existing, datasette_client.py:44)]
provides: [SQL-Interrupted 400 → QueryTimeoutError mapping]
affects: [tools/retrieval, tools/search, tools/query_table (all consume QueryTimeoutError via isinstance check)]
tech-stack:
  added: []
  patterns: [defensive JSON parse + scoped catch-all branch + from None traceback hygiene]
key-files:
  created: []
  modified:
    - src/mcp_zeeker/core/datasette_client.py
    - tests/test_datasette_client_retry.py
decisions:
  - "Branch is gated on status_code == 400 AND body.get('title') == 'SQL Interrupted' — exact-string + status pair. Vanilla 400s, non-dict bodies, and non-JSON bodies all fall through to the existing UpstreamCallFailed raise."
  - "No retry on the new branch: re-issuing the same query against a non-indexed scan times out the same way, and retrying amplifies upstream load during exhaustion (matches D-16 philosophy)."
  - "Locked error catalog (D3-12) was NOT modified — query_timeout was already in the catalog at index 8, and the canonical raise_query_timeout() helper in core/errors.py was already wired to QueryTimeoutError via isinstance checks in tool handlers."
metrics:
  completed: 2026-05-17
---

# Quick 260517-bki: Fix Datasette client error mapping (SQL-Interrupted 400 → query_timeout) Summary

One-liner: HTTP 400 with `{"title": "SQL Interrupted"}` now raises `QueryTimeoutError` instead of bare `UpstreamCallFailed`, so the agent reads upstream SQL time-limit exhaustion as `query_timeout` (recoverable query-shape problem) rather than `upstream_unavailable` (service-down).

## Production Incident

Discovered live in a Claude session on `zeeker-judgements.judgments_fragments` (81,812 rows, upstream index missing on `judgment_id`). Datasette's 1 second `sql_time_limit_ms` was exhausted on a full-scan filter, returning:

```
HTTP 400
{"ok": false, "error": "SQL query took too long...", "status": 400, "title": "SQL Interrupted"}
```

The client's catch-all on line 189-191 mapped this to bare `UpstreamCallFailed`, which the tool handler then mapped to `upstream_unavailable`. The agent gave up on a recoverable problem (LIMIT smaller scan window, or a different table) because the error code told it the upstream was unreachable.

Other fragments tables (`pdpc.enforcement_decisions_fragments` 1,711 rows, `sglawwatch.about_singapore_law_fragments` 2,454 rows) do NOT trip this — full-scan completes inside the 1s limit. The bug is specific to large + non-indexed fragments tables.

## Exact Source Diff in _request_with_retry

Inserted BEFORE the existing catch-all `UpstreamCallFailed` raise (now at line 199-201), AFTER the `if 200 <= resp.status_code < 300: return resp` check:

```python
if 200 <= resp.status_code < 300:
    return resp
# WR-260517-bki: Datasette signals upstream SQL time-limit exhaustion
# as HTTP 400 with {"title": "SQL Interrupted"}. Surface as
# QueryTimeoutError so agents read it as `query_timeout`, not
# `upstream_unavailable`. Scoped to 400 + explicit marker; vanilla 400s
# fall through. No retry (re-issuing will time out the same way).
if resp.status_code == 400:
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("title") == "SQL Interrupted":
        raise QueryTimeoutError(f"upstream SQL interrupted on {url}") from None
# D4-09 / 04-RESEARCH §3.7: same — pass through resp.status_code.
# The transport-error raise (httpx.RequestError above) keeps
# status=None via default since no HTTP response was parsed.
raise UpstreamCallFailed(
    f"upstream {resp.status_code} on {url}", status=resp.status_code
)
```

Design notes:
- `ValueError` catches `json.JSONDecodeError` (subclass) AND any other parse error from `httpx.Response.json()`; non-JSON 400 bodies fall through.
- `from None` suppresses the inner `resp.json()` frame from the traceback chain — keeps the exception clean for structlog and avoids hinting at internals.
- `isinstance(body, dict)` defends against the case where upstream returns a JSON list/string/null with status 400.
- No retry: re-issuing the same request will time out the same way (missing upstream index is not transient).

## New Tests Added

`tests/test_datasette_client_retry.py` gained three tests:

1. `test_sql_interrupted_400_raises_query_timeout` — positive case. Verifies `QueryTimeoutError` is raised AND `isinstance(excinfo.value, UpstreamCallFailed)` (subclass relationship preserved so existing `except UpstreamCallFailed:` handlers still catch this path). Also asserts no retry (1 request, 0 sleeps).
2. `test_vanilla_400_still_raises_upstream_call_failed` — scope check. JSON body without `title` key. Asserts `UpstreamCallFailed` AND `not isinstance(..., QueryTimeoutError)`.
3. `test_non_json_400_still_raises_upstream_call_failed` — defensive guard. `content=b"<html>..."` (non-JSON). Asserts the `try/except ValueError` around `resp.json()` lets the request fall through to the catch-all instead of bubbling a JSONDecodeError.

## Test Results

```
$ uv run pytest tests/test_datasette_client_retry.py -x
============================== 10 passed in 0.11s ==============================

$ uv run pytest -x
================= 475 passed, 14 skipped, 5 warnings in 7.49s ==================
```

Pass count: 10/10 in the targeted file (7 pre-existing + 3 new). Full suite: 475 passed, 14 skipped (all skips are live-network tests gated by `ZEEKER_LIVE=1`).

## Verification Audits

```
$ grep -n "SQL Interrupted" src/mcp_zeeker/core/datasette_client.py
187:            # as HTTP 400 with {"title": "SQL Interrupted"}. Surface as
196:                if isinstance(body, dict) and body.get("title") == "SQL Interrupted":

$ grep -nE "raise QueryTimeoutError" src/mcp_zeeker/core/datasette_client.py
158:                raise QueryTimeoutError(str(exc)) from exc
197:                    raise QueryTimeoutError(f"upstream SQL interrupted on {url}") from None
```

Both audits match the plan's `<verification>` block: two `SQL Interrupted` hits (comment + literal), two `raise QueryTimeoutError` sites (existing TimeoutException catch + new branch).

## Scope Negatives (what was NOT changed)

- `src/mcp_zeeker/core/errors.py` — untouched. The locked error catalog (D3-12) already contained `query_timeout` at index 8.
- `CATALOG` — untouched.
- `src/mcp_zeeker/tools/*.py` — untouched. Tool handlers already distinguish `QueryTimeoutError` via `isinstance(exc, QueryTimeoutError)` and call `raise_query_timeout()`. No caller changes needed because `QueryTimeoutError` is a subclass of `UpstreamCallFailed`.
- No new dependencies. `json` was already imported in `datasette_client.py` at line 17 (the `ValueError` catch obviates the need to use `json.JSONDecodeError` directly — `httpx.Response.json()` raises it as a subclass of `ValueError`).

## TDD Gate Compliance

This was executed as a single-task quick with bundled RED+GREEN+commit (matching the plan's `<action>` step A/B sequence). The RED step was confirmed before the source edit:

```
$ uv run pytest tests/test_datasette_client_retry.py::test_sql_interrupted_400_raises_query_timeout -x
FAILED tests/test_datasette_client_retry.py::test_sql_interrupted_400_raises_query_timeout
mcp_zeeker.core.datasette_client.UpstreamCallFailed: upstream 400 on /zeeker-judgements/judgments_fragments.json
```

GREEN step after source edit: all 10 tests pass.

## Commit

- `e4705ac` — `fix(quick-260517-bki-01): map Datasette SQL-Interrupted 400 to QueryTimeoutError`

## Deviations from Plan

None — the plan's `<action>` step A/B was executed verbatim, including the WHY comment text. The optional non-JSON sub-case was implemented as a separate third test (cleaner than a third sub-case in test 2) per the plan's "if included" allowance.

## Threat Flags

None. The new branch introduces no new trust boundary or attack surface — the SQL-Interrupted gate is exact-string match on an upstream-controlled field, and the resulting `QueryTimeoutError` message uses the same server-internal URL pattern as the sibling `UpstreamCallFailed` raise. The handler-level `raise_query_timeout()` emits the FIXED literal catalog message and discards the exception arg per INJ-05 / T-03-01, so no upstream string reaches the LLM-facing envelope.

## Self-Check: PASSED

- src/mcp_zeeker/core/datasette_client.py: FOUND (modified, branch present at line 187-197)
- tests/test_datasette_client_retry.py: FOUND (modified, 3 new tests present)
- Commit e4705ac: FOUND in git log
- All grep audits match the plan's `<verification>` block
- Full test suite green (475 passed, 14 skipped, 0 failed)
