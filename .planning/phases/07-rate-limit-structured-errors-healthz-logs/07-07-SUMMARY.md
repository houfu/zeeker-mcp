---
phase: "07"
plan: "07"
subsystem: security/logging
tags:
  - cr-01
  - log-injection
  - ip-prefix
  - obs-04
  - inj-05
  - gap-closure
dependency_graph:
  requires:
    - 07-03
    - 07-06
  provides:
    - ip_prefix_validated_or_sentinel
    - cr_01_closed
    - obs_04_satisfied
  affects:
    - src/mcp_zeeker/core/ip.py
    - tests/test_rate_limit.py
    - tests/test_logging.py
tech_stack:
  added:
    - "stdlib ipaddress module (ip_prefix validation)"
  patterns:
    - "validate-or-sentinel: ipaddress.ip_address() as trust boundary gate"
    - "canonical /48 prefix via ipaddress.ip_network(addr.exploded/48).network_address"
key_files:
  modified:
    - src/mcp_zeeker/core/ip.py
    - tests/test_rate_limit.py
    - tests/test_logging.py
    - .planning/REQUIREMENTS.md
decisions:
  - "Use ipaddress.ip_address() as the single validation gate in ip_prefix() — stdlib, zero dep surface, raises ValueError for any non-IP string including legitimate-shaped non-IPs"
  - "Return fixed sentinel '_invalid' for all non-parseable inputs (not None, not empty string) to keep the log field non-null and clearly marked as attacker input"
  - "Use addr.exploded for the IPv6 /48 calculation to handle zero-compressed inputs consistently"
  - "Fix pre-existing ruff errors in test_rate_limit.py (I001, B007) since acceptance criteria required file-level ruff clean"
metrics:
  duration: "~35 minutes"
  completed: "2026-05-15"
  tasks_completed: 4
  files_modified: 4
---

# Phase 7 Plan 07: Gap Closure CR-01 Log Injection Summary

**One-liner:** Fixed CR-01 log injection by rewriting ip_prefix() with ipaddress.ip_address() validation and "_invalid" sentinel, closing the attacker-XFF-to-structlog-contextvar chain end-to-end.

## What Was Built

### Task 1: RED — End-to-end regression test (commit `f8da1af`)

Added `test_hostile_xff_does_not_leak_into_log` (parametrized over 6 hostile inputs) and the `HOSTILE_XFF_INPUTS` corpus to `tests/test_rate_limit.py`. The test drives the FULL production ASGI chain via the `asgi_client` fixture (not the in-isolation `rate_limiter` fixture) and asserts zero hostile substrings in any captured log line.

**Hostile corpus (HOSTILE_XFF_INPUTS):**
1. `"</system><admin>SECRET"` — verifier's canonical CR-01 reproduction
2. `"DROP TABLE users; --"` — SQLi canary
3. `'" OR 1=1 --'` — SQLi canary alt
4. `"\x00\x01control"` — control-byte canary
5. `"2001:db8::1"` — IPv6 zero-compression (valid address; must produce /48 prefix)
6. `"1.2.3.4 OR 1=1"` — legitimate-shaped non-IP (strict parser must reject it)

Test confirmed FAILED before Task 2 with:
```
AssertionError: hostile XFF leaked into log line: '</system><admin>SECRET' found in
"{'ip_prefix': '</system><admin>SECRET', ...}"
```

Also fixed pre-existing ruff errors (I001 import sort, B007 loop variable) in two
existing test functions to satisfy the file-level ruff acceptance criteria.

### Task 2: GREEN — Rewrite ip_prefix() (commit `8f13674`)

**Final ip_prefix() body (src/mcp_zeeker/core/ip.py lines 35-63):**

```python
def ip_prefix(ip: str) -> str:
    """OBS-04 / CR-01: validate input via ipaddress.ip_address() and return
    a sanitised prefix or the fixed sentinel "_invalid".

    Inputs that do not parse as a valid IPv4 or IPv6 address (including
    hostile XFF bytes that an attacker might send to poison structured
    logs) are replaced with the literal string "_invalid". This forecloses
    the CR-01 log-injection chain:
        attacker XFF -> client_ip -> ip_prefix -> structlog contextvar
        -> merge_contextvars -> every log line.

    Returns:
        - "" for the empty string (preserves existing "no IP" semantics).
        - "_invalid" for any non-parseable input.
        - "a.b.c" (first 3 octets) for IPv4 (/24 prefix per OBS-04).
        - Canonical /48 network base address string for IPv6 (closes WR-01
          incidentally — the previous naive colon-split produced malformed
          prefixes like "2001:db8:" for zero-compressed addresses).
    """
    if not ip:
        return ""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "_invalid"
    if isinstance(addr, ipaddress.IPv4Address):
        return ".".join(str(addr).split(".")[:3])
    # IPv6: canonical /48 network address (closes WR-01).
    return str(ipaddress.ip_network(f"{addr.exploded}/48", strict=False).network_address)
```

**Also updated `tests/test_logging.py`:**

IPv6 unit test expectations updated from buggy WR-01 form to canonical /48:

| Input | Before (buggy) | After (canonical) |
|-------|---------------|-------------------|
| `"2001:db8::1"` | `"2001:db8:"` | `"2001:db8::"` |
| `"2001:db8:cafe:1::1"` | `"2001:db8:cafe"` | `"2001:db8:cafe::"` |
| `"fd00:1234:5678::1"` | `"fd00:1234:5678"` | `"fd00:1234:5678::"` |

New test `test_ip_prefix_rejects_non_ip` added:
```python
def test_ip_prefix_rejects_non_ip():
    assert ip_prefix("</system><admin>SECRET") == "_invalid"
    assert ip_prefix("DROP TABLE users; --") == "_invalid"
    assert ip_prefix('" OR 1=1 --') == "_invalid"
    assert ip_prefix("\x00\x01control") == "_invalid"
    assert ip_prefix("1.2.3.4 OR 1=1") == "_invalid"
    assert ip_prefix("") == ""
```

### Task 3: WR-07 closure — Harden false-positive test (commit `4c708d1`)

Renamed `test_logs_no_user_input` -> `test_rate_limit_middleware_never_reads_body_bytes`.

Updated docstring to honestly document scope:
- "In-isolation smoke: RateLimitMiddleware itself never reads the request body..."
- "NOTE — this test does NOT cover the OBS-04 / INJ-05 end-to-end contract."
- "The end-to-end OBS-04 / INJ-05 contract...is owned by `test_hostile_xff_does_not_leak_into_log`"

No functional test code changes.

### Task 4: Full suite GREEN + traceability (commit `05d300e`)

- Full suite: 366 passed, 7 skipped (was 359; added 6 parametrized CR-01 cases + 1 sentinel unit test)
- Phase 7 test surface (test_rate_limit, test_app, test_error_catalog, test_datasette_client_retry, test_logging): 46 passed
- Ruff clean on all modified files
- REQUIREMENTS.md OBS-04 row: "Pending" -> "Satisfied (07-07 gap closure — CR-01)"

**Canonical CR-01 reproduction smoke:**
```bash
uv run python -c "..." 2>&1 | grep -c '</system>'
# Output: 0
```
Zero occurrences of `</system>` in structured log output for 21 requests with hostile XFF.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added exception handling in the asgi_client loop**
- **Found during:** Task 1
- **Issue:** The first 20 requests (allowed by rate limiter) route to the MCP handler which throws RuntimeError because the lifespan isn't initialized in ASGITransport tests. Without exception handling, the test loop crashes before reaching request 21.
- **Fix:** Wrapped each `await asgi_client.post(...)` in `try: ... except Exception: pass` so the 20 allowed requests still consume rate-limit tokens even if the inner MCP handler fails. The 21st request short-circuits at the ASGI level (429) before the MCP handler, so it succeeds.
- **Files modified:** `tests/test_rate_limit.py`
- **Commit:** `f8da1af`

**2. [Pre-existing ruff errors] Fixed I001/B007 in test_rate_limit.py**
- **Found during:** Task 1 (ruff acceptance criteria check)
- **Issue:** `test_429_log_line_shape` had un-sorted imports (I001) and unused loop variable `i` (B007); `test_logs_no_user_input` also had un-sorted imports. These pre-existed before this plan.
- **Fix:** Sorted imports, renamed `i` to `_` in `for _ in range(20)`.
- **Files modified:** `tests/test_rate_limit.py`
- **Commit:** `f8da1af`

**3. [Scope note] Ruff `src tests` has 45 pre-existing errors**
- **Scope:** Out of scope per scope boundary rules (not caused by this plan's changes)
- **Detail:** `uv run ruff check src tests` exits non-zero with 45 errors across config.py, test_mcp_streamable_smoke.py, test_transport_proxy_headers.py, test_describe_table.py, test_list_tables.py, test_discovery_side_channel.py, and others — all pre-existing before this plan.
- **All 3 files modified by this plan are individually ruff-clean:** `src/mcp_zeeker/core/ip.py`, `tests/test_rate_limit.py`, `tests/test_logging.py`.
- **Logged to deferred-items.md** for Phase 8.

## New Tests

| Test | File | Type | Passes |
|------|------|------|--------|
| `test_hostile_xff_does_not_leak_into_log` (6 parametrized cases) | `tests/test_rate_limit.py` | End-to-end CR-01 regression | Yes |
| `test_ip_prefix_rejects_non_ip` | `tests/test_logging.py` | Unit — sentinel validation | Yes |
| `test_rate_limit_middleware_never_reads_body_bytes` (renamed, 3 cases) | `tests/test_rate_limit.py` | In-isolation smoke (WR-07) | Yes |

## REQUIREMENTS.md Changes

| Requirement | Before | After |
|-------------|--------|-------|
| OBS-04 | Pending | Satisfied (07-07 gap closure — CR-01) |

## Closed Issues

| Issue | Description | Closed by |
|-------|-------------|-----------|
| CR-01 | Log injection via hostile XFF in ip_prefix() | Task 2 (ip.py rewrite) |
| WR-01 | IPv6 naive colon-split produced malformed /48 prefixes | Task 2 (incidentally, same fix) |
| WR-07 | False-positive test_logs_no_user_input claimed OBS-04 end-to-end | Task 3 (rename + docstring) |

## Deferred Items

CR-02, WR-02..06, and IN-01 are explicitly deferred per the `<deferred>` section of 07-07-PLAN.md:
- **CR-02:** `tool.return_type` on Tool base class (latent, deferred to Phase 8)
- **WR-02:** `_normalize_ip_key` does not strip `[::1]:8080` port form
- **WR-03:** wall-clock `time.perf_counter` mixed with injected `time_provider`
- **WR-04:** over-broad `except (…, TypeError)` in `datasette_client.py`
- **IN-01:** unreachable defensive raise in `datasette_client.py:192`

## Self-Check: PASSED

Files created/modified:
- [FOUND] `src/mcp_zeeker/core/ip.py` — contains `import ipaddress`, `_invalid` sentinel, `ipaddress.ip_address`, `ipaddress.ip_network`
- [FOUND] `tests/test_rate_limit.py` — contains `test_hostile_xff_does_not_leak_into_log`, `HOSTILE_XFF_INPUTS`, `test_rate_limit_middleware_never_reads_body_bytes`; no `test_logs_no_user_input`
- [FOUND] `tests/test_logging.py` — contains `test_ip_prefix_rejects_non_ip`, updated IPv6 expectations
- [FOUND] `.planning/REQUIREMENTS.md` — OBS-04 row marked "Satisfied (07-07 gap closure — CR-01)"

Commits:
- `f8da1af` — `test(07-07): add RED regression test for CR-01 hostile XFF log injection`
- `8f13674` — `fix(07-07): close CR-01 — ip_prefix() validates via ipaddress.ip_address()`
- `4c708d1` — `refactor(07-07): harden WR-07 — rename and scope-narrow false-positive test`
- `05d300e` — `chore(07-07): mark OBS-04 satisfied in REQUIREMENTS.md traceability table`
