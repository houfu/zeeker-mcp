---
status: partial
phase: 08-full-tests-24h-soak
source: [08-VERIFICATION.md]
started: 2026-05-15T06:58:12Z
updated: 2026-05-15T06:58:12Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Run the full 24h soak via workflow_dispatch on the soak.yml workflow
expected: p50 < 300ms, p95 < 1.5s, max RSS < 256 MB, zero PoolTimeout cascade entries in latency.csv, daily rollover observed, report.py exits 0
result: [pending]
prerequisites:
- Fix CR-02 in scripts/soak/report.py:236 (add `if not latency_path.exists(): return 1` guard, mirroring the rss.csv .exists() check at line 237). Without this, a uvicorn-start failure produces an unhelpful traceback instead of a clean exit-1.
- Consider WR-01 (unbounded latency_log list) and WR-04 (sleep 5 not a readiness probe) before launching the actual 24h run.

### 2. Run live integration tests against data.zeeker.sg
expected: All 6 live tests pass, including test_live_describe_table, test_live_list_tables, test_live_query_table, test_live_fetch, test_live_search, test_live_list_databases
result: [pending]
command: `ZEEKER_LIVE=1 uv run pytest -m live -v`
prerequisites:
- Fix CR-01 in tests/test_live_golden_path.py:119-120 (`envelope.data` is a `list[dict]`, not a `dict` — change `"columns" in envelope.data` and `envelope.data["columns"]` to operate on `envelope.data[0]`). Without this fix, test_live_describe_table raises TypeError every nightly run.

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

Both items are blocked on confirmed code defects (CR-01, CR-02) flagged in `.planning/phases/08-full-tests-24h-soak/08-REVIEW.md`. Recommended sequencing:

1. `/gsd-code-review 8 --fix` — auto-apply fixes for CR-01 and CR-02 (and optionally WR-01..04)
2. Trigger soak.yml via `workflow_dispatch` on GitHub Actions; observe the report.md artifact
3. Run `ZEEKER_LIVE=1 uv run pytest -m live -v` locally OR wait for the next nightly run of live-tests.yml
4. `/gsd-verify-work 8` once both tests above have evidence
