---
phase: 8
slug: full-tests-24h-soak
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-15
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: distilled from `08-RESEARCH.md` § "Validation Architecture" (lines 1178–1253).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 1.3 (auto mode) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, lines 41-47) |
| **Quick run command** | `uv run pytest -x -q` |
| **Full suite command** | `uv run pytest` |
| **Live cmd (TEST-02)** | `ZEEKER_LIVE=1 uv run pytest -m live -p no:xdist` |
| **Soak smoke cmd** | `uv run python -m scripts.soak.run_soak --duration 60 --concurrency 5` |
| **Soak full cmd (pre-release)** | `uv run python -m scripts.soak.run_soak --duration 86400 --concurrency 50` |
| **Soak report gate** | `uv run python -m scripts.soak.report --max-p50-ms 300 --max-p95-ms 1500 --max-rss-mb 256` |
| **Estimated runtime (full unit)** | ~30 seconds |
| **Estimated runtime (smoke soak)** | ~60 seconds + ~5s report |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/test_dependency_footprint.py tests/test_app_lifespan_contract.py -x` (the two NEW tests likeliest to break with code changes)
- **After every plan wave:** `uv run pytest -x -q` (full unit suite, ~30s)
- **Before `/gsd-verify-work`:** Full unit suite green AND smoke soak gate passes (`run_soak --duration 60 --concurrency 5 && report --max-p50-ms 300 --max-p95-ms 1500 --max-rss-mb 256`)
- **Pre-release (manual):** `soak.yml` workflow_dispatch — full 24h soak with daily-rollover assertion
- **Max feedback latency:** 60 seconds for unit suite; 65 seconds for smoke soak gate

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 08-01 | 0 | NFR-04 | — | Runtime deps == 6 named packages | unit | `pytest tests/test_dependency_footprint.py::test_runtime_deps_match_locked_set -x` | ❌ W0 NEW | ⬜ pending |
| TBD | 08-01 | 0 | NFR-04 | — | Dev deps == 4 named packages | unit | `pytest tests/test_dependency_footprint.py::test_dev_deps_match_locked_set -x` | ❌ W0 NEW | ⬜ pending |
| TBD | 08-01 | 0 | (CR-02 carryover) | — | Lifespan raises RuntimeError (not AttributeError) for non-FunctionTool | unit | `pytest tests/test_app_lifespan_contract.py -x` | ❌ W0 NEW | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (filters) | T-INPUT | All 13 filter operators compile correctly | unit | `pytest tests/test_filter_compiler.py -x` | ✅ extend | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (envelope) | — | Envelope shape per tool | unit | `pytest tests/test_envelope_snapshot.py -x` | ✅ exists | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (hidden-table) | T-DATA-LEAK | list_tables strips hidden | unit | `pytest tests/test_hidden_data_enforcement.py::test_list_tables_strips_hidden -x` | ❌ W0 NEW | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (hidden-column) | T-DATA-LEAK | describe_table strips hidden columns | unit | `pytest tests/test_hidden_data_enforcement.py::test_describe_table_strips_hidden_columns -x` | ❌ W0 NEW | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (rate-limit burst) | T-DOS | 20-burst window enforced | unit | `pytest tests/test_rate_limit.py -k burst -x` | ✅ exists | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (rate-limit sustained) | T-DOS | 60/min window enforced | unit | `pytest tests/test_rate_limit.py -k sustained -x` | ✅ exists | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (rate-limit daily) | T-DOS | 5000/24h window + UTC rollover | unit | `pytest tests/test_rate_limit.py -k daily -x` | ✅ exists | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (errors) | — | Error code mapping (all 11) | unit | `pytest tests/test_error_catalog.py -x` | ✅ exists | ⬜ pending |
| TBD | 08-02 | 1 | TEST-01 (cursor) | T-INPUT | Cursor qhash mismatch rejection | unit | `pytest tests/test_cursor.py::test_shape_mismatch_raises_invalid_cursor -x` | ✅ exists | ⬜ pending |
| TBD | 08-03 | 2 | TEST-03 (snapshot keys) | T-DATA-LEAK | row.keys ∩ HEAVY_COLUMNS == ∅ for all 6 tools | unit (snapshot) | `pytest tests/test_envelope_snapshot.py -x` | ✅ extend | ⬜ pending |
| TBD | 08-03 | 2 | TEST-03 (retrieved_content) | T-DATA-LEAK | retrieved_content.keys ⊆ HEAVY_COLUMNS | unit (snapshot) | `pytest tests/test_envelope_snapshot.py -k retrieved_content -x` | ✅ exists | ⬜ pending |
| TBD | 08-03 | 2 | TEST-06 (hostile inputs) | T-INJECT | 9 canaries × 3 tools × 3 surfaces (81 cases); 0 leaks | unit | `pytest tests/test_hostile_inputs_consolidated.py -x` | ✅ extend matrix | ⬜ pending |
| TBD | 08-03 | 2 | TEST-04 (1500-frag) | — | 1500-fragment walk completes correctly | unit | `pytest tests/tools/test_retrieval_fragment_join.py::test_1500_fragment_walk_synthetic -x` | ✅ document under TEST-04 | ⬜ pending |
| TBD | 08-04 | 3 | TEST-02 (live golden path) | — | Live golden path per tool against `data.zeeker.sg` | integration | `ZEEKER_LIVE=1 pytest tests/test_live_golden_path.py -p no:xdist -x` | ❌ W1 NEW | ⬜ pending |
| TBD | 08-05 | 3 | TEST-05 + NFR-01..03 (smoke) | T-DOS | Smoke soak (1 min, 5 concurrent); p95 < 1.5s; RSS < 256 MB | smoke | `python -m scripts.soak.run_soak --duration 60 --concurrency 5 && python -m scripts.soak.report --max-p50-ms 300 --max-p95-ms 1500 --max-rss-mb 256` | ❌ W2 NEW | ⬜ pending |
| TBD | 08-05 | 3 | TEST-05 (24h, daily rollover) | T-DOS | Full 24h soak; daily rollover observed | manual / pre-release | `python -m scripts.soak.run_soak --duration 86400 --concurrency 50` | ❌ W2 NEW | ⬜ pending |
| TBD | 08-05 | 3 | NFR-01 (p50) | — | p50 < 300ms in soak report | post-soak | `python -m scripts.soak.report --max-p50-ms 300` | ❌ W2 NEW | ⬜ pending |
| TBD | 08-05 | 3 | NFR-01 (p95) | — | p95 < 1.5s in soak report | post-soak | `python -m scripts.soak.report --max-p95-ms 1500` | ❌ W2 NEW | ⬜ pending |
| TBD | 08-05 | 3 | NFR-02 (concurrency) | T-DOS | 50 concurrent sustained without errors | soak driver | implicit in driver `--concurrency 50`; `report` exit 0 | ❌ W2 NEW | ⬜ pending |
| TBD | 08-05 | 3 | NFR-03 (RSS) | — | RSS < 256 MB throughout soak | post-soak | `python -m scripts.soak.report --max-rss-mb 256` | ❌ W2 NEW | ⬜ pending |
| TBD | 08-06 | 4 | NFR-05 (allowlist doc) | — | README documents Anthropic IP allowlist | manual / doc review | `grep -q 'Anthropic IP' README.md` | ❌ W3 NEW (extends README) | ⬜ pending |
| TBD | 08-06 | 4 | NFR-05 (single-worker doc) | — | README documents single-worker | manual / doc review | already present at `README.md:71-75` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Task IDs are TBD — populated by `/gsd-planner` when each PLAN.md task is materialized; the planner MUST overwrite each TBD with the canonical `{phase}-{plan}-{task}` ID and propagate the row to the plan's `tasks` block.*

---

## Wave 0 Requirements

- [ ] `tests/test_dependency_footprint.py` — covers NFR-04 (NEW; uses stdlib `tomllib` to assert exact 6-runtime + 4-dev tuples)
- [ ] `tests/test_app_lifespan_contract.py` — covers Phase 7 carryover CR-02 (NEW; asserts `RuntimeError` not `AttributeError` for non-`FunctionTool`)
- [ ] `tests/test_hidden_data_enforcement.py` — covers TEST-01 hidden-data sweep on `list_tables` and `describe_table` edges (NEW)
- [ ] `tests/test_live_golden_path.py` — covers TEST-02 (NEW; gated by `pytest.mark.live` + `ZEEKER_LIVE=1`)
- [ ] `scripts/soak/__init__.py` + `run_soak.py` + `workload.py` + `rss_sampler.py` + `report.py` — covers TEST-05 + NFR-01/02/03 (NEW; pure-stdlib + already-pinned `httpx` only — preserves NFR-04)
- [ ] `tests/_corpus/soak_workload.py` — shared workload definition (NEW)
- [ ] No new fixtures in `tests/conftest.py` — single-plan-touch already enforced; Phase 8 reuses existing fixtures only

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full 24h soak with daily-rollover crossing UTC midnight | TEST-05 | 24h wall-clock cannot run on every PR; CI cost; observability rather than pass/fail | Trigger `soak.yml` workflow_dispatch pre-release; verify `daily_rollover_observed=True` in report and at least one `429` rate drop within ±60s of UTC midnight |
| Anthropic IP-allowlist documentation correctness | NFR-05 | Authoritative source is Anthropic operator surface; not testable from this repo | Operator review of README "Deployment" section against current Anthropic-published allowlist (re-check at Phase 9 submission) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (4 NEW unit-test files + soak harness package)
- [ ] No watch-mode flags
- [ ] Feedback latency < 65s for the smoke-soak gate; < 30s for the unit suite
- [ ] `nyquist_compliant: true` set in frontmatter once all PLAN.md tasks reference rows above

**Approval:** pending
