# Phase 6.1 — Deferred Items

Pre-existing issues encountered during Plan 06.1-01 execution but **OUT OF SCOPE**
per the SCOPE BOUNDARY rule (fix only issues directly caused by the current task).
These were not introduced by 06.1-01 and predate the gap-closure scope.

## Pre-existing Ruff Findings

`uv run ruff check src/ tests/` reports 45 errors and 6 format violations on
files **NOT modified by Plan 06.1-01**:

- `src/mcp_zeeker/core/filter_compiler.py` — would-reformat
- `src/mcp_zeeker/tools/discovery_models.py` — would-reformat
- `tests/test_transport_stateless_session.py` — would-reformat
- `tests/tools/test_describe_table.py` — would-reformat
- `tests/tools/test_discovery_side_channel.py` — would-reformat
- `tests/tools/test_list_tables.py` — would-reformat (E501 on line 212)
- E501 line-length violations on `src/mcp_zeeker/config.py` lines
  174/175/182 (TABLE_DESCRIPTIONS) — already flagged in Plan 06-02 SUMMARY
  and confirmed pre-existing via `git stash && ruff check` in Plan 06-01.

**All 8 files modified by Plan 06.1-01 pass `ruff check` + `ruff format
--check` cleanly:**

- src/mcp_zeeker/core/citation.py
- src/mcp_zeeker/core/metadata_cache.py
- src/mcp_zeeker/core/search.py
- src/mcp_zeeker/tools/retrieval.py
- tests/test_citation_synthesis.py
- tests/test_heavy_column_upstream.py
- tests/test_metadata_cache.py
- tests/tools/test_query_table.py

A dedicated lint-hygiene plan (Phase 7 or later) should run `ruff check
--fix` + `ruff format` over the whole tree and audit the resulting diff in
one focused commit — that's the right place to consolidate the pre-existing
debt rather than smearing it across feature plans.
