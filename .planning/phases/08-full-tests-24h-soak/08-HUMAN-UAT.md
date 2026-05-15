---
status: partial
phase: 08-full-tests-24h-soak
source: [08-VERIFICATION.md]
started: 2026-05-15T06:58:12Z
updated: 2026-05-15T07:30:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Run the full 24h soak via workflow_dispatch against mcp.zeeker.sg
expected: p50 < 300ms, p95 < 1.5s, max RSS < 256 MB, zero PoolTimeout cascade entries in latency.csv, daily rollover observed, report.py exits 0
result: [pending]
prerequisites:
- Set `SOAK_BYPASS_TOKEN` as a GitHub Actions repo secret (`openssl rand -hex 32`).
- Set the SAME `SOAK_BYPASS_TOKEN` value in the production container's environment (docker-compose env_file or operator-managed secrets). Restart the container so the env is picked up.
- Confirm preflight: the workflow's first step calls `/healthz` and `/admin/metrics` with the token; will abort if either fails.
ops_note: |
  This is a real 50-concurrent load test against the live deployment. Coordinate
  with ops on the run window. After the soak finishes, unset SOAK_BYPASS_TOKEN
  on the production container and restart so the bypass cannot fire in
  steady-state operation.

### 2. Run live integration tests against data.zeeker.sg
expected: All 6 live tests pass, including test_live_describe_table, test_live_list_tables, test_live_query_table, test_live_fetch, test_live_search, test_live_list_databases
result: [pending]
command: `ZEEKER_LIVE=1 uv run pytest -m live -v`
prerequisites: (none — CR-01 was fixed in commit 6654c71)

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

CR-01 and CR-02 (the two blockers identified at original verification) are
now resolved. The soak workflow now points at the production endpoint via
soak-token bypass (commits 46a3732, de581a2, 68ed782 in the soak-against-prod
work). Remaining items are operational, not code defects:

1. Generate `SOAK_BYPASS_TOKEN` (one time): `openssl rand -hex 32`
2. Set it in both places (GitHub Actions secret + prod container env)
3. Restart prod container so env is picked up
4. Trigger `soak.yml` via `workflow_dispatch` on the Actions UI; observe the
   `soak-results` artifact at the end (latency.csv, rss.csv, report.md)
5. After the run, unset the env on prod and restart to close the bypass surface
6. Run `ZEEKER_LIVE=1 uv run pytest -m live -v` locally OR wait for the next
   nightly run of `live-tests.yml`
7. `/gsd-verify-work 8` once both runs have evidence
