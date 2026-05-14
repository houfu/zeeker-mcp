---
phase: 03-structured-retrieval-url-keyed-fetch
audited_at: 2026-05-14
asvs_level: 1
threats_total: 19
threats_closed: 19
threats_open: 0
threats_accepted: 3
status: secured
register_origin: PLAN.md threat_model blocks (one per plan, all 4 plans)
block_on: any_open_mitigate
auditor_stance: adversarial — every mitigation verified by direct grep / source inspection
---

# Phase 03 Security Audit — Structured Retrieval + URL-Keyed Fetch

## Audit summary

19 threats declared across Plans 03-01 / 03-02 / 03-03 / 03-04. All 19 resolve:
16 `mitigate` threats verified present in source via the exact grep recipes
declared in the threat register, and 3 `accept` threats documented in the
accepted-risks log with PLAN justifications verbatim.

No unregistered attack surface flags. Plan 03-04 SUMMARY (line 234) declares
"Threat Flags: None" and Plans 03-01/02/03 SUMMARY entries surface no new
attack surface beyond the register.

Recent code-review-fix cycle (2026-05-14, seven commits between `6744e98` and
`e9a77c2`) strengthens — not weakens — the relevant mitigations: T-03-01 /
T-03-06 (WR-01 rejects float/bool on INTEGER ops); T-03-11 (WR-05 `is not None`
preserves `columns=[]` distinguishability); T-03-13 (WR-03 subtracts
HEAVY_COLUMNS in the configured_light branch); upstream JSON robustness
(WR-06). The audit verifies the post-fix state.

Live UAT evidence (`03-HUMAN-UAT.md`, completed 2026-05-14) corroborates three
INJ-05 attack shapes (T-03-11, T-03-15, T-03-19) at the wire level, but this
audit's status determination relies on static source evidence as required.

## Threat verification table

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-03-01 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/core/filter_compiler.py` — grep `'f"invalid_filter_op:.*{'` returns 0 hits. All 5 `invalid_filter_op:` strings are fixed literals (lines 129, 135, 139, 159, 168, 177, 191). WR-01 (commit `3ff608e`) additionally rejects float/bool BEFORE `int()` (lines 157-160) to prevent silent truncation. Numeric-coercion raises use `from None` (lines 168, 177) to suppress `__cause__` chain — protecting against value text leaking via traceback formatters. |
| T-03-02 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/core/visibility.py` line 145 — `_visible_columns` is a single set subtraction (`set(t.columns) - hidden_columns_for(database, table)`); no separate `if column in HIDDEN_COLUMNS:` pre-check exists in either `core/filter_compiler.py` or `core/visibility.py` (grep shows only docstring/comment mentions warning against such a check, lines 12-16 + 139-141). `compile_filters` re-checks against `visible_columns` set (line 114) — same set-membership path as the handler. |
| T-03-03 | Tampering | mitigate | CLOSED | `src/mcp_zeeker/core/filter_compiler.py` lines 133-140 — `isinstance(f.value, list)` outer check + `all(isinstance(v, (str, int, float)) for v in f.value)` per-element check, both raising the same fixed-literal `invalid_filter_op: in/notin value must be a flat list of str/int/float`. |
| T-03-04 | Tampering | mitigate | CLOSED | `src/mcp_zeeker/core/datasette_client.py` lines 194-198 — `get_table_rows` uses `params=[("_shape", "objects"), *params]` (list-of-tuples handed to httpx for URL encoding); no f-string-into-URL paths. `compile_filters` returns `list[tuple[str, str]]` (line 73). Path segment `f"/{database}/{table}.json"` (line 196) is route construction — `database` is validated against `ALLOWED_DATABASES` and `table` against `_visible_tables` BEFORE this call. |
| T-03-05 | DoS | accept | CLOSED (accepted) | See accepted-risks log entry T-03-05 below. |
| T-03-06 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` — grep `'f"invalid_filter_op:.*{'` returns 0 hits. The two `invalid_filter_op:` strings in the file (lines 169, the belt-and-suspenders limit clamp) are fixed literals. `upstream_unavailable: upstream call failed` (lines 289, 393) is a fixed literal with `from None` suppression. `invalid_cursor:` strings (line 260 path via `decode_cursor`) propagate from `core/cursor.py` which holds two fixed literals. |
| T-03-07 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` — grep `'filter_value'` returns 0. The only structlog binding (`log.debug("query_table_invoked", ...)`, lines 276-281) binds `database`, `table`, `filter_count` — no `filter_value`. |
| T-03-08 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` validation order (lines 181-197): `_resolve_table` (181) → `_visible_columns` (184) → per-field `raise_unknown_column` calls for filters (189-190), sort (191-194), columns (195-197). All three paths route through the same `raise_unknown_column` helper (single emission point in `core/visibility.py:56`). Counter-patch test `tests/tools/test_retrieval_side_channel.py` (referenced in plan 03-02 SUMMARY, all 4 tests GREEN). |
| T-03-09 | Tampering | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` line 105-112 — `Field(default=50, ge=1, le=200)`. Plus a belt-and-suspenders clamp at handler entry (lines 168-169) that catches direct Python callers bypassing Pydantic dispatch. Threat register row's "Pydantic Field(ge=1, le=200) rejects limit=201 before handler body" verified. |
| T-03-10 | Tampering | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` line 192 — `sort.lstrip("-")` strips ONLY the leading minus; remainder checked against `_visible_columns` (lines 193-194) before being passed to Datasette as `_sort` (line 244) or `_sort_desc` (line 242). httpx URL-encodes; Datasette parameterizes. No SQL string concat. |
| T-03-11 | Tampering | mitigate | CLOSED | `src/mcp_zeeker/core/cursor.py` lines 100-101 — `hashlib.blake2b(canonical_shape_str_value.encode(), digest_size=8).hexdigest()` produces 16-hex-char digest; `decode_cursor` lines 135-137 compare `digest_part != expected` and raise the fixed-literal mismatch error. WR-05 (commit `40bdc40`) ensures `columns=[]` and `columns=None` produce distinct shapes via `is not None` (line 85). |
| T-03-12 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/core/cursor.py` — grep `'f"invalid_cursor:'` returns 0 hits. Only two fixed-literal strings exist: `"invalid_cursor: cursor is malformed"` (line 133) and `"invalid_cursor: cursor does not match current request shape"` (line 137). Decode failure uses `raise ... from None` (line 133) to suppress `__cause__` — base64 input cannot leak via traceback. |
| T-03-13 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` lines 219-238 — row reshape partitions via `config.HEAVY_COLUMNS`. Default branch (columns is None) subtracts HEAVY_COLUMNS BOTH from the configured-light path (line 231, post-WR-03 commit `aa6c5c0`) AND from the fallback path (line 234). Explicit-columns branch (lines 237-238) partitions into light_to_emit / heavy_to_emit. Reshape step (lines 296-303) builds `row` only from `light_to_emit` keys; heavy columns appear ONLY under `retrieved_content` and ONLY when `heavy_to_emit` is non-empty. D3-19 snapshot tests enforce `set(row.keys()) ∩ HEAVY_COLUMNS == ∅`. |
| T-03-14 | DoS | accept | CLOSED (accepted) | See accepted-risks log entry T-03-14 below. |
| T-03-15 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/core/visibility.py` line 78 — `def raise_not_found(database: str, table: str) -> NoReturn:` — NO `url` parameter. Error string (line 84) is the fixed literal `f"not_found: No row found in {database}.{table} for the given URL"`. Grep `'raise_not_found.*url'` against both `visibility.py` and `retrieval.py` returns 0 hits. Call site at `tools/retrieval.py:401` passes only `(database, table)`. |
| T-03-16 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` lines 420-426 — `log.warning("fetch_ambiguous_url", database=database, table=table, match_count=len(rows))` — NO `url=` kwarg. Strict grep `'fetch_ambiguous_url'` filtered to lines containing `\burl=` (kwarg form) returns 0 hits. The three lines matched by a loose grep are all the literal event-name substring `fetch_ambiguous_url` (one is a docstring step description, one is an inline INJ-05 contract comment, one is the actual `log.warning` first positional argument) — none bind the URL value. |
| T-03-17 | Information Disclosure | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` lines 408-414 — `emit_cols = (visible - config.HEAVY_COLUMNS) - fk_to_exclude` where `fk_to_exclude` is populated from `config.FRAGMENT_PARENTS[...]["parent_fk"]` (line 413). `visible` already excludes hidden columns (e.g., `id`) via `_visible_columns` / `hidden_columns_for`. Reshape (line 433) builds the emit dict only from `emit_cols` keys. Snapshot test `test_fetch_strips_heavy_and_fragment_columns` (test_fetch.py) asserts the invariant. |
| T-03-18 | Tampering | mitigate | CLOSED | `src/mcp_zeeker/tools/retrieval.py` line 389 — `params: list[tuple[str, str]] = [(f"{url_col}__exact", url), ("_size", "2")]` — URL passed verbatim to httpx as a query param value. No `urllib.parse.urlparse` / no `lower()` / no `strip()` / no normalization. `?utm=test` appended to a known URL changes the exact-string match key and falls through to the zero-row not_found path. `_FETCH_DESCRIPTION` (line 327-328) documents this contract: "URL match is exact string equality (no normalization)." |
| T-03-19 | Information Disclosure | accept | CLOSED (accepted) | See accepted-risks log entry T-03-19 below. |

## Accepted risks log

### T-03-05 — DoS via large filter list / 5 KB filter values

**Plan disposition:** accept
**Plan justification (verbatim):** "Phase 7's rate limiter is primary defense. Document as accepted risk."
**Scope:** A caller could submit a filter array with hundreds of clauses, or any single filter value approaching 5 KB. Phase 3 has no per-request size cap on filter values; httpx will URL-encode and forward to Datasette, and `compile_filters` walks the entire list before raising.
**Mitigating context:** Anonymous-tier rate limits (20/burst, 60/minute, 5000/IP/day) cap per-IP volume. Phase 7 ships the rate limiter as the primary defense layer.
**Re-audit trigger:** If Phase 7 ships and the rate limiter is bypassed in any tier, OR if any per-tool size constraint is added elsewhere (creates inconsistency).

### T-03-14 — DoS via cursor walk on extremely long page chains

**Plan disposition:** accept
**Plan justification (verbatim):** "Phase 7's rate limiter is primary defense. Document as accepted risk."
**Scope:** Each page is a separate MCP call. A motivated caller could walk an arbitrarily long page chain by repeatedly calling `query_table` with the previous response's `next_cursor`. Phase 3 imposes no per-request page-walk cap.
**Mitigating context:** Each cursor reuse is a separate billable MCP call against the anonymous-tier rate limits (20/burst, 60/minute, 5000/IP/day). At 5000 calls/day the practical depth is bounded.
**Re-audit trigger:** Same as T-03-05 — Phase 7 rate-limit changes.

### T-03-19 — Presence side-channel on unsupported table

**Plan disposition:** accept
**Plan justification (verbatim):** "unsupported_table_for_fetch and unknown_table are DISTINCT errors by design (FETCH-04). _resolve_table runs FIRST so hidden tables return unknown_table before URL_COLUMNS lookup. Document as accepted risk."
**Scope:** A caller can distinguish "this table exists but is not URL-keyed" (`unsupported_table_for_fetch`) from "this table doesn't exist or is hidden" (`unknown_table`). For tables visible in `list_tables` this is not new information; for hidden tables there is NO leak because `_resolve_table` runs first and emits `unknown_table` BEFORE the URL_COLUMNS lookup.
**Verification:** `src/mcp_zeeker/tools/retrieval.py` validation order in `fetch`: line 378 `await _resolve_table(database, table)` precedes line 383 `url_col = url_column_for(database, table)`. A hidden table thus hits `raise_unknown_table` and never reaches the URL_COLUMNS check.
**Re-audit trigger:** If `_resolve_table` order changes in the fetch handler (would re-introduce presence leak on hidden tables).

## Unregistered flags

None.

Plan 03-04 SUMMARY (line 234) explicitly states "Threat Flags: None" — the
implementation matches the plan's threat register without introducing
unanticipated attack surface. Plans 03-01 / 03-02 / 03-03 SUMMARY entries
likewise contain no `## Threat Flags` section with unregistered surface.

## Live evidence (supplementary — not load-bearing for status)

Phase 3 human UAT and F-4 wire-level dry-run (recorded in `03-HUMAN-UAT.md`,
completed 2026-05-14) exercised three INJ-05 attack shapes against the
deployed instance at https://mcp.zeeker.sg/mcp/ and confirmed:

- Hostile URL on unsupported table (T-03-19 contract enforced) — no URL echo
- Cursor shape-mismatch (T-03-11 qhash) — cursor token + sort value not echoed
- Hostile URL on not_found (T-03-15) — URL absent from error body

The static source evidence in the table above is the authoritative basis for
each CLOSED status; the wire-level evidence corroborates.

## Audit trail

| Date | Auditor | Action | Outcome |
|------|---------|--------|---------|
| 2026-05-14 | gsd-secure-phase | Initial audit — verified 19 threats post-code-review-fix cycle (commits 6744e98..e9a77c2) | SECURED — all 16 mitigate threats CLOSED; 3 accept threats documented |
