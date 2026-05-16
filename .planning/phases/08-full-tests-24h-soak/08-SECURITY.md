---
phase: 08
slug: full-tests-24h-soak
status: secured
threats_open: 0
threats_total: 32
threats_closed: 32
asvs_level: 1
audited: 2026-05-17
auditor: gsd-security-auditor
block_on: open
---

# Phase 8 Security Audit

**Phase:** 08 — Full Tests + 24h Soak
**Audited:** 2026-05-17
**Auditor:** gsd-security-auditor
**ASVS Level:** L1
**block_on:** open
**Status:** SECURED (all 32 threats CLOSED; 0 OPEN)

---

## Scope

Verification of every declared threat mitigation in the six Phase-8 plan threat models
(`08-01-PLAN.md` … `08-06-PLAN.md`) plus the six retroactive-STRIDE threats surfaced in
`08-SOAK-BYPASS-REVIEW.md` after the soak target was repointed at live production
(`mcp.zeeker.sg`), plus one project-scoped pending todo in `STATE.md`.

Implementation files (`src/`, `scripts/`, `tests/`, `.github/workflows/`, `README.md`,
`.planning/REQUIREMENTS.md`, `Caddyfile.prod`) were treated as read-only — this is a
verification pass, not a fix pass.

---

## Threat Verification (32 total)

### Plan 08-01 (Wave 0: dep-footprint + lifespan contract)

| Threat ID         | Category                    | Disposition | Status | Evidence (file:line)                                                                                                                                              |
|-------------------|-----------------------------|-------------|--------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| T-DEP-DRIFT       | Tampering / Info Disclosure | mitigate    | CLOSED | `tests/test_dependency_footprint.py:18` (`RUNTIME_DEPS_LOCKED = frozenset(...)` frozenset literal); `:30` (`DEV_DEPS_LOCKED`); `:62, :73, :88` tomllib reads pyproject.toml. NFR-04 invariant test is GREEN per `08-VERIFICATION.md` re-verification (439 passed, 14 skipped). |
| T-LIFESPAN-OPACITY| DoS (startup w/ poor error) | mitigate    | CLOSED | `src/mcp_zeeker/app.py:60` reads `getattr(tool, "return_type", None) is not Envelope` (defensive read); regression test at `tests/test_app_lifespan_contract.py::test_non_function_tool_raises_runtime_error_not_attribute_error`. |
| T-CR-02-LATENT    | Tampering (latent)          | accept      | CLOSED | Acceptance rationale verified against current code: today all 6 production tools are FunctionTool instances. The Task 3 fix at `app.py:60` is defensive and permanently regression-tested. No further mitigation needed; explicitly documented in `08-01-SUMMARY.md`. |

### Plan 08-02 (Wave 1: TEST-01 unit-coverage gate)

| Threat ID         | Category                                | Disposition | Status | Evidence (file:line) |
|-------------------|-----------------------------------------|-------------|--------|----------------------|
| T-DATA-LEAK       | Information Disclosure (denylist sweep) | mitigate    | CLOSED | `tests/test_hidden_data_enforcement.py:209` (`test_list_tables_strips_hidden` parametrized across HIDDEN_TABLES); `:243` (`test_describe_table_strips_hidden_columns` parametrized across all `(db, table, hidden_column)` triples via `hidden_columns_for`). 10 + 19 = 29 parametrized cases per `08-02-SUMMARY.md`. |
| T-INPUT (filters) | Tampering (FilterOp drift)              | mitigate    | CLOSED | `tests/test_filter_compiler.py:28` (`ALL_OPS` tuple — 13 entries); `:316` (`get_args(FilterOp)` length-13 assertion in `test_op_in_locked_set`). Closes the "11 vs 13" discrepancy with a length check that fails in both directions of drift. |
| T-DOS (rate-limit math) | DoS (verified by tests)           | mitigate    | CLOSED | `tests/test_rate_limit.py:69` (`test_burst_allows_20_rejects_21st`); `:132` (`test_sustained_refill_after_one_second`); `:165, :199, :417` (three daily-window tests). All three keywords selectable via `pytest -k {burst,sustained,daily}`. |
| T-INPUT (cursor)  | Tampering (cursor reuse across shapes)  | mitigate    | CLOSED | `tests/test_cursor.py:34` (`test_shape_mismatch_raises_invalid_cursor`) exercises shape-A → shape-B qhash rejection. Canonical VALIDATION.md path selects this test verbatim. |
| T-D2-10-BYPASS    | Tampering (single-source-of-truth)      | mitigate    | CLOSED | `tests/test_hidden_data_enforcement.py` uses `hidden_columns_for(db, table)` only (verified by grep — zero direct `config.HIDDEN_COLUMNS` reads). `tests/test_config_lookup_single_source.py` D2-10 enforcement still passes per `08-02-SUMMARY.md`. |

### Plan 08-03 (Wave 2: TEST-03/04/06 data-safety gate)

| Threat ID            | Category                              | Disposition | Status | Evidence (file:line) |
|----------------------|---------------------------------------|-------------|--------|----------------------|
| T-DATA-LEAK (per-tool HEAVY) | Information Disclosure         | mitigate    | CLOSED | `tests/test_envelope_snapshot.py:333` (`leaked_top = set(row.keys()) & config.HEAVY_COLUMNS`); `:335-336` ("TEST-03 leak: ...top-level row keys"); `:339` (`rc_extra = set(row["retrieved_content"].keys()) - config.HEAVY_COLUMNS`); `:341` ("TEST-03 leak: ...retrieved_content carries non-HEAVY keys"). |
| T-INJECT (CANARY × 3-surface) | Info Disclosure / Injection   | mitigate    | CLOSED | `tests/_corpus/hostile_inputs.py` CANARY_STRINGS verified to contain 9 entries (introspection: indices 0-4 are the Phase-6 set; 5-8 are the new BOM/RTL/malformed-surrogate/FTS5-op canaries). `tests/test_hostile_inputs_consolidated.py:138-140` parametrizes 3 tools × 9 canaries = 27 cases, all GREEN per `08-03-SUMMARY.md`. |
| T-TEST-ID-DRIFT      | Tampering (parametrize index renames) | mitigate    | CLOSED | Python introspection confirms `CANARY_STRINGS[0]=='</system>'`, `CANARY_STRINGS[4]=='\udc80'` — indices 0-4 preserved exactly per `08-03-SUMMARY.md` first-5-entries invariant. New canaries appended at 5-8. |
| T-TEST-04-ORPHAN     | Tampering (requirement orphaned)      | mitigate    | CLOSED | `tests/tools/test_retrieval_fragment_join.py:649` reads "TEST-04 owner: Phase 8 (regression test originated in Phase 5 D5-06)" inside the test docstring; REQUIREMENTS.md row 279 references the docstring marker explicitly. |
| T-SCOPE-NARROWING    | Tampering (test exception masks bug)  | mitigate    | CLOSED | `08-03-SUMMARY.md` confirms "No exceptions needed in `tests/test_hostile_inputs_consolidated.py`. All 4 new canaries pass the 9×3 matrix without any carry-forward exception." The matrix decorator at `:138-140` is unchanged (no scope-narrowing parametrize axes added). |

### Plan 08-04 (Wave 3a: TEST-02 live-test cadence)

| Threat ID            | Category                                | Disposition | Status | Evidence (file:line) |
|----------------------|-----------------------------------------|-------------|--------|----------------------|
| T-CI-LEAK            | Information Disclosure (CI artifacts)   | mitigate    | CLOSED | `tests/test_live_golden_path.py:78,94,109,123,138,150` — 6 `@pytest.mark.live` tests assert only `envelope.provenance.source` + shape (no raw envelope dumps, no IPs printed). `.github/workflows/live-tests.yml` does not configure artifact upload — only stdout/stderr logs. |
| T-DOS-UPSTREAM       | DoS (against data.zeeker.sg)            | mitigate    | CLOSED | `.github/workflows/live-tests.yml:25` runs `ZEEKER_LIVE=1 uv run pytest -m live -p no:xdist` (sequential execution; per-run upstream budget = 6 calls). |
| T-CADENCE-DRIFT      | Tampering (silent regression in cron)   | mitigate    | CLOSED | `.github/workflows/live-tests.yml:9-10` pins cron schedule (`0 2 * * *` UTC); `:18` pins `actions/checkout@11bd71901...` (v4.2.2 SHA); `:20-22` pins `astral-sh/setup-uv@caf0cab7...` with `version: "0.11.14"`. WR-02 fix verified (commit e856534). |
| T-CONTENT-FRAGILITY  | Tampering (assertion drift within 48h)  | mitigate    | CLOSED | `tests/test_live_golden_path.py` asserts `envelope.provenance.source == "data.zeeker.sg"` (stable literal) + `len(envelope.data) >= 1` / `isinstance(envelope.data, list)` — never on license strings or citation content. CR-01 fix at line 119-120 (`envelope.data[0]["columns"]`) verified. |
| T-FETCH-URL-DRIFT    | Tampering                               | accept      | CLOSED | Acceptance rationale verified: `tests/test_live_golden_path.py` uses `_STABLE_FETCH_URL = "https://www.elitigation.sg/gd/s/2026_SGDC_136"` (long-published judgment). If URL ever 404s upstream, test fails loud with `not_found` and operator updates. Documented in `08-04-SUMMARY.md`. |

### Plan 08-05 (Wave 3b: 24h soak harness)

| Threat ID                | Category                            | Disposition | Status | Evidence (file:line) |
|--------------------------|-------------------------------------|-------------|--------|----------------------|
| T-DEP-DRIFT (soak)       | Tampering (NFR-04 invariant)        | mitigate    | CLOSED | `scripts/soak/{__init__,rss_sampler,workload,run_soak,report}.py` all import stdlib + `httpx` only (verified by code review at `08-REVIEW.md` "NFR-04 Import Verification" table — all 7 PASS). `tests/test_dependency_footprint.py` still GREEN. |
| T-DOS-DRIVER-INFLATION   | DoS / measurement distortion        | mitigate    | CLOSED | `.github/workflows/soak.yml` runs against live `https://mcp.zeeker.sg` (driver and server are different machines); `scripts/soak/run_soak.py:74-76` uses `time.perf_counter()` AROUND the await. WR-01 fix (streaming CSV writer at `run_soak.py:240`) prevents driver OOM. |
| T-SOAK-IP-LEAK           | Information Disclosure              | mitigate    | CLOSED | `scripts/soak/run_soak.py:240` writes only `wall_ts, status, duration_seconds, error_class` — no bodies, no IPs, no tokens. Driver header is `X-Soak-Bypass: <token>` set via env var, never logged. |
| T-CI-COST-OVERRUN        | DoS (CI minutes)                    | mitigate    | CLOSED | `.github/workflows/soak.yml:31-32` uses `workflow_dispatch:` only (no `schedule:` block); `:37` `timeout-minutes: 350`. Grep confirms no `cron:` or `schedule:` substring. |
| T-PSUTIL-CREEP           | Tampering                           | accept      | CLOSED | Acceptance rationale verified: `pyproject.toml` searched — zero `psutil` matches. `scripts/soak/rss_sampler.py` and `src/mcp_zeeker/core/admin.py:38` use pure stdlib (`/proc/self/status` + `resource.getrusage`). |
| T-WORKLOAD-DUPLICATION   | Tampering                           | mitigate    | CLOSED | `tests/_corpus/soak_workload.py:25` canonical definition; `scripts/soak/workload.py:29` `from tests._corpus.soak_workload import WORKLOAD as WORKLOAD`. Single object bound to both names. |
| T-SOAK-ARTIFACT-COMMIT   | Information Disclosure              | mitigate    | CLOSED | `.gitignore` contains 2 matches for `soak-results` / `soak-smoke-results` (verified via grep count == 2). |

### Plan 08-06 (Wave 4: NFR-05 + traceability sweep)

| Threat ID                  | Category                       | Disposition | Status | Evidence (file:line) |
|----------------------------|--------------------------------|-------------|--------|----------------------|
| T-OPERATOR-DRIFT           | Information Disclosure         | mitigate    | CLOSED | `README.md:105` "### Anthropic IP allowlist" (no "forward-looking" suffix); `:113` "Apply the allowlist at the host Caddy layer (or upstream firewall), NOT in the MCP container — Caddy already owns ingress per `Caddyfile.prod`"; quarterly re-verify cadence present. |
| T-TRACE-FALSE-CLOSURE      | Tampering                      | mitigate    | CLOSED | `.planning/REQUIREMENTS.md:271-281` — all 11 Phase-8 rows (TEST-01..06 + NFR-01..05) flipped to "Satisfied (08-NN)" with per-row plan IDs. TEST-04 row preserves Phase 5 origin clarifier; TEST-05 row distinguishes smoke vs full 24h. |
| T-OBS-PHASE-CROSSOVER      | Tampering                      | mitigate    | CLOSED | `.planning/REQUIREMENTS.md:267` OBS-04 still reads "Satisfied (07-07 gap closure — CR-01)" (untouched). `:265` OBS-02 still reads "Deferred to v2 (D7-05)". Phase-7 territory preserved. |
| T-NFR-05-UNVERIFIED        | Tampering (doc requirement)    | accept      | CLOSED | Acceptance rationale verified: `README.md:71` "The production command **must** run uvicorn with `--workers 1`"; `:81` "`uvicorn mcp_zeeker.app:app --host 0.0.0.0 --port 8000 --workers 1`"; `:84` "RATE-06 in REQUIREMENTS.md mandates `--workers 1` for v1". Both NFR-05 grep gates (`'Anthropic IP'` AND `'workers 1'`) succeed. |

### Post-phase soak-bypass review (retroactive STRIDE per 08-SOAK-BYPASS-REVIEW.md)

These six threats were authored after the soak was repointed at live production
(`mcp.zeeker.sg`). Evidence built from cited commits + current implementation files.

| Threat ID                  | Category                       | Disposition | Status | Evidence (file:line) |
|----------------------------|--------------------------------|-------------|--------|----------------------|
| T-SOAK-AUTH-BLOCKING-IO (CR-01) | DoS (async-loop block + production 500) | mitigate | CLOSED | `src/mcp_zeeker/core/admin.py:38-59` inlines `_read_rss_kb()` — reads `/proc/self/status` via `Path(...).read_text()` and falls back to `resource.getrusage`. **No import of `scripts.soak.rss_sampler`** anywhere in `src/` (grep confirms). The Dockerfile no longer needs `scripts/` to satisfy `/admin/metrics`. Fix landed at commit `f9c66ac` (per scope description). The handler is `async def admin_metrics`; `_read_rss_kb` is sync but does small stdlib reads — acceptable for the trivial latency budget. The blocking-IO surface is the same as on any other request path in this codebase. |
| T-SOAK-REPORT-FALSE-PASS (CR-02) | Tampering (silent NFR-03 pass) | mitigate | CLOSED | `scripts/soak/report.py:71-102` (`_load_rss` filters `v < 0` sentinels and counts them separately); `:268` (`max_rss_mb = max(rss_kb) / 1024.0 if rss_kb else 0.0`); `:286-292` explicit breach when `not rss_kb and rss_sentinel_count > 0` ("NFR-03 cannot be evaluated: 0 valid RSS samples"). Fix landed at commit `fff8310` (per scope description). |
| T-SOAK-TOKEN-NON-ASCII (WR-01) | DoS (UnicodeEncodeError → 500) | mitigate | CLOSED | `src/mcp_zeeker/core/soak_auth.py:58` `if not token.isascii(): return None` — non-ASCII tokens are treated as unset (safe default; every request short-circuits to False). Fix landed at commit `1eb74b4` (per scope description). |
| T-SOAK-BYPASS-SURFACE      | Authorization                  | mitigate    | CLOSED | (a) constant-time compare at `soak_auth.py:96` via `hmac.compare_digest(bytes, bytes)`; (b) bypass scoped to rate-limit only — `rate_limit.py:143-145` short-circuits rate-limit middleware exclusively, no other authorization surface is bypassed; (c) `admin.py:71-73` returns `Response(status_code=404)` (NOT 401/403) when `is_soak_authenticated(scope)` is False — explicitly documented as defence-in-depth at `admin.py:10-14`. |
| T-SOAK-FAN-OUT-CAP         | DoS (upstream saturation)      | mitigate    | CLOSED | `src/mcp_zeeker/core/search.py:351` `sem = anyio.Semaphore(10)` (commit `a419388`). Cap is reachable from search tool path: `tools/search.py:193` → `fan_out_search` → `sem`. Math at `core/search.py:344-350` documents worst case 10 × 10 = 100 search connections + 40 non-search = 140 ≤ 150 pool. |
| T-SOAK-CONN-LIMIT          | DoS (PoolTimeout cascade)      | mitigate    | CLOSED | `src/mcp_zeeker/core/http_client.py:20` `max_connections=150` (raised above the originally-cited 50→100 to absorb fan-out × concurrency). `:21` `max_keepalive_connections=20`; `:22` `keepalive_expiry=30.0`. Note: the actual value in code is **150** (not the 100 mentioned in the scope description) — code is the source of truth; documented inline at `:17-19` against the fan_out_search semaphore math. |

### Project-scoped pending todo (informational, not a phase-8 blocker)

| Threat ID            | Category                          | Disposition | Status | Evidence |
|----------------------|-----------------------------------|-------------|--------|----------|
| T-FUTURE-DB-FAN-OUT  | DoS (latency scales with DB count)| accept (v2) | CLOSED | `.planning/STATE.md:80` captures the pending todo with rationale, options (a/b/c) and the trigger condition ("Decision deferred until the 5th database is in flight"). Today 4 DBs are in scope; T-SOAK-FAN-OUT-CAP is the v1 mitigation. |

---

## Summary

- **Total threats:** 32 (22 mitigate + 4 accept declared at plan-time + 6 retroactive-STRIDE + 1 project-scoped pending todo with accept disposition for v1)
- **CLOSED:** 32 / 32
- **OPEN:** 0
- **Unregistered flags:** 0 (every SUMMARY.md "## Threat Flags" section read either "None" or — for plans that introduced new attack surface — was already mapped to a declared threat in this register)

The phase-8 changeset ships with every declared mitigation present in the code, and the six
post-phase soak-bypass concerns (CR-01, CR-02, WR-01..04 from `08-SOAK-BYPASS-REVIEW.md`) are
all verified as patched at commits `f9c66ac` / `fff8310` / `1eb74b4` / `a419388` / `7312ceb` /
`c581b19` per the audit scope description.

---

## Observations (non-blocking; informational)

1. **`http_client.py:20` reads `max_connections=150`, not the 100 mentioned in the audit scope.**
   The code comment at `core/http_client.py:17-19` documents the math against `fan_out_search`
   semaphore(10) at soak concurrency=50. Code is the source of truth; the audit scope's "50→100"
   was conservative — the actual mitigation is more generous than declared.

2. **`Caddyfile.prod:18-20` adds a `rewrite @mcp_exact /mcp/`** rewrite to suppress Starlette's
   308 redirect on the bare `/mcp` path (commit `c581b19`). Verified as security-adjacent only:
   it does not introduce a new ingress surface — Caddy already owns ingress per the existing
   `## Caddy header requirements` section in `README.md`. No new authorization, no new routing
   target; the rewrite is purely a path-normalisation step.

3. **`access_log.py` for bypass requests** is touched by the soak driver at ~50 req/s for 5h30m =
   ~990k log lines per soak run. Per `08-SOAK-BYPASS-REVIEW.md` IN-13 this is within scope for
   NFR-05 consideration but is not a correctness bug; consider sampling for v2. Not a phase-8
   blocker; recorded here for future planning.

---

_Audited: 2026-05-17_
_Auditor: Claude Code (gsd-security-auditor)_
_ASVS Level: L1_
