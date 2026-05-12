# Pitfalls Research — Zeeker MCP Connector

**Domain:** Remote MCP server proxying a public Datasette legal-data API to LLM clients, anonymous-tier, submission target `anthropics/claude-for-legal`
**Researched:** 2026-05-13
**Confidence:** HIGH for MCP / JSON-RPC / Datasette / X-Forwarded-For; MEDIUM for `claude-for-legal` reviewer behavior (one authoritative source: CONNECTORS.md); MEDIUM for injection-resistance "what breaks envelope labeling" (synthesis from multiple security writeups, no single canonical post-mortem).

This document is opinionated. The PRD already covers the obvious moves (denylists, envelope, opt-in heavy columns, trailing sentence). Everything below is what defensive PRD writers in this exact intersection still tend to miss.

---

## Critical Pitfalls

### Pitfall 1: Opaque cursor that isn't actually opaque

**What goes wrong:**
The PRD says `query_table.cursor` is "opaque cursor passed through from Datasette's `_next`." Implementers reach for "opaque" and then either (a) URL-encode/JSON-wrap it into something Datasette can't read back, or (b) leak it as the literal `_next` value, which encodes a sort-key fragment of the *last visible row* — so when the caller passes a cursor that referenced a now-hidden row, results skip or repeat.

A subtler failure: Datasette's `_next` is sort-order-sensitive. If a caller paginates with `sort=date_desc`, then changes `sort` on the next call while reusing the cursor, Datasette will silently misinterpret it — you'll get a 200 response with wrong rows, not an error.

**Why it happens:**
"Opaque" is treated as a passthrough contract rather than a binding contract. The server doesn't bind the cursor to the *query shape* (database/table/filters/sort/columns).

**How to avoid:**
- Cursor = base64(json({"next": "<datasette _next>", "qhash": "<sha256 of normalized request>"})). Reject cursors whose `qhash` doesn't match the current request's shape with a clear `invalid_cursor` error.
- Document the binding in the tool description so callers understand: "the cursor is valid only with the same filters/sort/columns."
- Add a property test: random walk through pagination with a stable sort produces unique rows with no gaps.

**Warning signs:**
- "Sometimes results repeat / sometimes I see fewer rows than expected" in integration test output.
- Datasette returns a `truncated: true` envelope on a page that wasn't supposed to be truncated — the cursor encoded a value that pushed past `max_returned_rows`.
- Tests that pass with a single fixed sort but fail when sort is varied.

**Phase to address:** M3 (Structured retrieval) — must be in by the time `query_table` ships.

---

### Pitfall 2: Datasette's silent 1,000-row truncation masquerading as a complete result

**What goes wrong:**
Datasette's default `max_returned_rows` is 1,000. Any underlying SQL — including the joins our server issues for `*_fragments` — that produces > 1,000 rows returns the first 1,000 with `"truncated": true` and **no `next` cursor**. From the caller's perspective this looks like a complete final page. For a long judgment with 1,200 paragraph fragments, paragraphs 1,001+ are silently invisible.

The same applies to `/-/search.json` with a high `size`: > 1,000 results truncate.

**Why it happens:**
The PRD specifies `query_table` default limit 50 / max 200, which is well under 1,000 and lulls implementers into ignoring `truncated`. But our *server-side* fragment-join query may scan a parent's full fragment list to enforce ordering before slicing — that scan can hit the cap.

**How to avoid:**
- Read `truncated` from every Datasette response. If true and we didn't intend it, surface a structured `upstream_truncated` warning inside the envelope (`pagination.truncated: true` already exists in the PRD — use it honestly, don't just always set it false).
- For fragment joins, never SELECT * from a fragment table; always paginate by `(parent_fk = ?, order_by > ?)` with our own LIMIT below 1,000.
- Add a regression test: a synthetic parent with 1,500 fragments must paginate fully via `query_table` cursor walking.

**Warning signs:**
- A `judgments_fragments` query for a long judgment returns exactly the same row count as a shorter judgment — both capped at the default page size.
- `pagination.truncated` is always `false` in production logs but live data has documents > 1,000 fragments.

**Phase to address:** M5 (Fragments). Don't ship the fragment join until truncation is observably handled.

---

### Pitfall 3: `/-/search.json` results leaking hidden-table titles

**What goes wrong:**
Datasette's site-wide search hits every searchable table by default and returns each hit with `database` and `table` fields populated. If `sglawwatch.metadata` or `sglawwatch.schema_versions` happens to be FTS-indexed (they often are, by accident, in tools that auto-index everything), a `search` call will surface those rows' titles/snippets, exposing internal-table content to the LLM. Even with our post-hoc stripping, an attacker who *guesses* hidden table names can probe the absence/presence pattern via timing or hit counts.

A second leak surface: error messages. If `query_table(database="sglawwatch", table="metadata")` returns `"table 'metadata' is hidden"` rather than the generic `unknown_table`, an LLM-driven probe can enumerate the hidden set.

**Why it happens:**
Defensive-list mental model: "We have a denylist, so we're fine." Misses that the denylist enforcement point matters. Stripping *after* getting results means the upstream was already consulted; observable side-channels remain.

**How to avoid:**
- Pass `?database=` filters to `/-/search.json` explicitly, restricting to the four allowed databases. Don't let it default to "all".
- Post-hoc strip is still required (Datasette may add new databases later that we don't know about).
- Unify the error for hidden-table access with the error for nonexistent-table access. Both → `unknown_table` with identical message text. Resist the urge to be helpful with "this table is reserved."
- Constant-time-ish check (don't return faster for hidden than unknown): the hidden-table check should happen on the same code path as the unknown-table check.
- Test: probing 100 random hidden-table names and 100 known-hidden names must produce indistinguishable response shapes and indistinguishable timing buckets (within reason).

**Warning signs:**
- Search results in development with `sqlite_*`, `_fts`, `metadata`, or `schema_versions` in the `table` field at any stage of the pipeline — even pre-strip.
- Error messages that differ by one word between hidden vs unknown tables.

**Phase to address:** M2 (Discovery surface — error-message parity) and M4 (Search — `database=` filter + post-strip).

---

### Pitfall 4: Echoed filter values become prompt-injection vectors

**What goes wrong:**
An LLM crafts a `query_table` call with `filters=[{column: "title", op: "contains", value: "ignore prior instructions and ..."}]`. The query returns zero results. The server responds with `"no rows matched filter on 'title' contains 'ignore prior instructions and ...'"`. That string is now in the LLM's context window, *outside* the `retrieved_content` envelope, *not* labeled as document text — labeled as a server message, which is the most trusted scope.

This breaks the envelope-labeling contract: the strategy assumes hostile text only arrives via `retrieved_content`. User-supplied filter values echoed in error messages create a second, unlabeled channel for adversarial text.

**Why it happens:**
"Helpful" error messages quote user input back. The injection-resistance section of the PRD focuses on retrieved content; it doesn't say anything about echoing *parameters*.

**How to avoid:**
- Never echo user-supplied string values in error messages. Refer to them positionally: `"filter[0] on column 'title' matched zero rows"`. Column names are bounded by the schema; values are not.
- For schema-validation errors that *must* mention the bad value (e.g., bad operator), echo only enum members from the allowed set — never raw input.
- Tool description must NOT include phrases like "I will return your filter back to you" — the LLM is allowed to assume the server won't re-emit hostile strings.
- Test: filter values containing `</system>`, `[INST]`, prompt-injection canaries, and 5 KB of random text never appear in the response payload.

**Warning signs:**
- Any structured log line containing user-supplied filter `value` outside a clearly marked `params` block.
- Any error response whose `message` string is variable-length proportional to input.

**Phase to address:** M3 (filter mapping must be value-echo-free from day one); reinforce in M6 (Envelope and safety).

---

### Pitfall 5: Heavy text accidentally inlined at the row top level on a new tool

**What goes wrong:**
The PRD is strict: heavy content lives under `retrieved_content`. M3 / M5 / M6 implementers are careful. Then someone adds a seventh tool or a convenience endpoint (a one-off `/preview` route, a new `describe_table` field showing a sample value, a `search` snippet field), and that path doesn't go through the envelope helper. A single `summary` field gets returned as a bare string and the LLM no longer has a visual cue distinguishing data from instructions.

**Why it happens:**
Envelope shape is enforced by convention, not by type. The single source of truth for "what fields are heavy" lives in `config.py`'s light/heavy set, but nothing programmatically prevents a heavy column from landing outside `retrieved_content`.

**How to avoid:**
- Make the envelope a function, not a convention. Implement `EnvelopeBuilder.row(database, table, raw_row)` that *partitions* columns by the light/heavy config and refuses to emit heavy columns outside `retrieved_content`. All response paths must go through this builder.
- Snapshot tests against a corpus of fixtures: every emitted row from every tool, asserting `set(row.keys()) ∩ HEAVY_COLUMNS == ∅` and `set(row["retrieved_content"].keys()) ⊆ HEAVY_COLUMNS`.
- Lint rule (custom Ruff or AST check): no return statement in a tool handler returns a dict that isn't from `EnvelopeBuilder`.
- The trailing sentence is also a single source: `TOOL_TRAILER` constant. CI check: every registered tool's description ends with `TOOL_TRAILER`. Add a test.

**Warning signs:**
- A new tool's PR diff touches response serialization but doesn't touch `EnvelopeBuilder`.
- `git grep -n 'content_text\|full_text\|html_raw' src/` finds them in handler-level code rather than only in the envelope module.

**Phase to address:** M6 (Envelope and safety) — establish the EnvelopeBuilder API; enforced as a CI check from M6 onward.

---

### Pitfall 6: X-Forwarded-For trusted blindly → rate-limit bypass

**What goes wrong:**
The PRD says "client IP (X-Forwarded-For aware)." Naïve implementations do `request.headers["X-Forwarded-For"].split(",")[0]` and use that for the rate-limit bucket key. A direct-to-origin attacker (or a misconfigured proxy that doesn't strip incoming XFF) can spoof a fresh IP per request, getting infinite calls. Worse, an attacker can flood with thousands of distinct spoofed values, exhausting the in-memory bucket store (memory DoS).

A second variant: the deployment doc says "TLS termination is the operator's responsibility." If the operator's reverse proxy doesn't *set* XFF (vs. just *passing it through*), all anonymous traffic shares the proxy's IP as the bucket key — a single noisy client trips the rate limit for everyone.

**Why it happens:**
XFF feels like "the standard way to get the real IP." It isn't a security primitive — it's a hint, only trustworthy when the immediate upstream is trusted.

**How to avoid:**
- Configuration: `TRUSTED_PROXY_DEPTH` integer (default 1, meaning "trust one hop"). Parse XFF right-to-left, drop the last `TRUSTED_PROXY_DEPTH` entries, then take the rightmost remaining entry. If XFF is missing or shorter than expected, fall back to the direct socket peer.
- Document the operator contract: the proxy MUST overwrite (not append) XFF, OR set a separate trusted header (e.g., `Forwarded` or a private `X-Real-IP`). Pin the variable name in `config.py`.
- Cap the bucket store: LRU eviction with a hard ceiling (e.g., 100k keys). Eviction policy must NOT reset live buckets; only evict idle ones.
- For the daily ceiling, store bucket state with a monotonic created-at timestamp and TTL-evict after 24h; do not rely on wall-clock alone.
- Test: requests with crafted `X-Forwarded-For: 1.2.3.4, 5.6.7.8` headers from the same TCP peer all map to the same bucket key when deployed behind one trusted hop.

**Warning signs:**
- The bucket store map size grows unboundedly during a 24h soak.
- Rate-limit test that sends the same crafted XFF header from different TCP peers shows them sharing a bucket (when they shouldn't) or NOT sharing (when they should).
- A single 429 from prod log includes a different IP-prefix on every line of a single user's session.

**Phase to address:** M7 (Rate limiting and errors). Deploy with `TRUSTED_PROXY_DEPTH=1` and a documented operator contract.

---

### Pitfall 7: 429 retry storms — `Retry-After` mismatched to bucket refill

**What goes wrong:**
The server returns 429 with `Retry-After: 60` because that's how often the bucket fills, but the bucket is actually a 20-burst / 1-token-per-second model — so a polite client that respects `Retry-After: 60` will pull 60 tokens at once after waiting, blow through the burst, and get another 429 immediately. Worse, multiple clients all synchronizing on 60s create periodic dogpile traffic.

A second failure: returning `Retry-After` in *seconds* but the docs/tool-description says *milliseconds* (or vice versa) — the LLM client retries 1000× too fast or too slow.

**How to avoid:**
- `Retry-After` value = time until *next single token* is available (typically 1s for sustained-refill exhaustion), not "time until full bucket." For daily-cap exhaustion, return time-until-next-24h-window-rollover.
- Always seconds (integer). Document explicitly in tool descriptions and error.data.
- Include `retry_after_seconds` in the structured error payload too, so callers don't have to parse the header.
- Add jitter advisory in the tool description: "Add 0-25% jitter before retrying to avoid synchronized retries."
- Test: simulate 10 concurrent clients all hitting 429, verify retries don't synchronize into a thundering herd.

**Warning signs:**
- A burst of 429s in logs every N seconds, all clustered at the same wall-clock second.
- Single client gets repeated 429 in a row after waiting the full `Retry-After`.

**Phase to address:** M7 (Rate limiting and errors).

---

### Pitfall 8: Fragment-parent join — ambiguous URL columns, multi-match parents, soft-deletes

**What goes wrong:**
The fragment-parent join is "look up the parent's internal PK by URL, then query the fragment table by FK." Failure modes that defensive PRD writers commonly miss:

1. **Multiple matches**: two parent rows happen to share a `source_url` (republication, mirror, corrected version). The query returns one PK arbitrarily, fragments come from whichever row SQLite happened to scan first — non-deterministic across requests.
2. **Soft-deleted parents**: parent has a `deleted_at` or `is_published=0`, fragment rows remain in the DB. Naive join returns orphaned fragment content; envelope provenance points to a parent the caller can't `fetch`.
3. **Ordering ties**: `ordinal=NULL` rows, or two fragments with `ordinal=5` (data quality issue upstream). Without a tiebreaker, page boundaries flip-flop between requests.
4. **Order column type confusion**: `ordinal=10` comes before `ordinal=2` if sorted as TEXT.

**How to avoid:**
- Multi-match: SELECT the parent by URL with a deterministic tiebreaker (`ORDER BY updated_at DESC, id ASC LIMIT 1`). If the count is > 1, log a warning with the URL; consider returning `ambiguous_parent` for v2.
- Treat all parent rows as live unless `config.py` per-table says otherwise; for v1, don't filter by soft-delete (data team's responsibility), but verify with sample queries against each `FRAGMENT_PARENTS` entry that no soft-deleted rows exist in practice. Document this assumption in `config.py`.
- Always sort fragments by `(order_by, id)` — even though `id` is hidden from output, it's a stable tiebreaker.
- Force numeric coercion at the SQL level: `ORDER BY CAST(ordinal AS INTEGER), id`. Verify the underlying schema's column type for each `order_by` entry; document in `FRAGMENT_PARENTS` config.

**Warning signs:**
- Fragment ordering tests pass deterministically locally but flake in CI.
- A `query_table` on `judgments_fragments` filtered by a known judgment URL returns a different row order on consecutive calls.

**Phase to address:** M5 (Fragments). The deterministic-tiebreaker must land before this milestone closes.

---

### Pitfall 9: Datasette FTS user-input escaping

**What goes wrong:**
The `search` tool passes the user's `query` straight through to `/-/search.json`. SQLite FTS5 treats characters like `"`, `(`, `*`, `:`, and operator keywords (`AND`, `OR`, `NOT`, `NEAR`) specially. A query like `Section 5(a)` raises an FTS syntax error → 400 from upstream → our server emits `query_timeout` or `upstream_unavailable`, neither of which is right. Worse, a query containing `OR table:metadata` could (depending on Datasette config) leak into a column-targeted search against a hidden FTS column.

**How to avoid:**
- Escape FTS user input by wrapping in double quotes and doubling any internal double-quotes: `f'"{query.replace(chr(34), chr(34)*2)}"'`. This treats the whole query as a phrase. Document the behavior: "search performs phrase matching across the indexed fields."
- If we want operator support later (`AND`/`OR`/quoted phrases), implement it explicitly with a parser; never pass raw FTS5 syntax through.
- Map FTS syntax errors from upstream to a clean `invalid_query` error code in our catalog (add this to the error catalog in Section 12).

**Warning signs:**
- Live search test fails on queries with `'`, `"`, `(`, `:`, `*` in them.
- A 400 from Datasette comes back as `upstream_unavailable` to the caller.

**Phase to address:** M4 (Search). Update error catalog to include `invalid_query`.

---

### Pitfall 10: JSON-RPC error shape drift / Claude Code's strict schema validation

**What goes wrong:**
FastMCP handles JSON-RPC framing for us, but it's easy to define a tool whose `inputSchema` uses `anyOf` / `oneOf` / `allOf` at the top level — Claude Code strictly rejects these schemas in v2.0.21+, while Claude Desktop tolerates them. Result: the connector "works in dev" (Desktop) and silently fails to register tools in Claude Code (the registry's primary client). The schema also must be Draft 2020-12 compliant and fully self-contained (no external `$ref`).

A second flavor: returning errors as Python exceptions and letting FastMCP serialize them generically — losing our structured error catalog (`unknown_database` etc.) in favor of a vague `-32603 Internal error`.

**How to avoid:**
- Constrain `inputSchema` to flat `type: "object"` with `properties` and `required`; if you'd reach for `anyOf`, model it as a discriminator string parameter instead.
- Pydantic models for tool inputs, but with `model_config = {"extra": "forbid"}` and explicit field types — no `Union[Foo, Bar]` at the top level. Verify the generated JSON schema doesn't contain top-level `anyOf`.
- Define a custom error class that carries `code`, `message`, `data` and a FastMCP-aware serializer; map all our error catalog entries through it.
- CI check: validate each tool's inputSchema against the MCP 2025-06-18 spec and reject `anyOf/oneOf/allOf` at top level.
- Acceptance test: launch the server, run Claude Code's `list-tools` against it, assert all six tools appear with full schemas.

**Warning signs:**
- Tool registration logs show "schema validation skipped" in the client.
- Error responses in Claude Code have generic codes (`-32603`) instead of our string codes.
- Schema diff: top-level `anyOf` appears after refactoring.

**Phase to address:** M1 (Skeleton transport) — set the constraint before any tool ships; verified in M2 onward.

---

### Pitfall 11: Streamable HTTP / SSE fallback negotiation

**What goes wrong:**
The MCP spec deprecated standalone SSE on 2025-03-26 in favor of Streamable HTTP, but Claude Code and other clients still attempt SSE fallback when Streamable HTTP fails. Implementations that "support both" by mounting separate `/sse` and `/mcp` endpoints often:
- Return HTML 404 to a GET `/mcp` (instead of a 405 or a valid SSE upgrade) — breaks fallback in some clients.
- Don't validate `Origin` header → CSRF risk for clients that hit the server from a browser context.
- Don't handle the `Mcp-Session-Id` header → session continuity breaks across reconnects.
- Have a strict CORS policy that blocks the `Mcp-Session-Id` header from being read by browser clients.

**How to avoid:**
- Single endpoint `/mcp` that supports both POST (request/response) and GET (open SSE stream). Return 405 on unsupported methods, not 404 or HTML.
- Implement and persist `Mcp-Session-Id` per the spec.
- Validate `Origin` header against an allow-list (config-driven). Reject browser-originating requests from unknown origins.
- CORS: include `Mcp-Session-Id` in `Access-Control-Expose-Headers`.
- Test against both Claude Code and Claude Desktop directly before submission — fixtures aren't enough.

**Warning signs:**
- Cursor / Claude Code logs "MCP server returned 404 HTML response."
- Session resumption tests pass locally but fail when proxied via cloudflared/ngrok.
- Browser-based MCP test client can't read session ID.

**Phase to address:** M1 (Skeleton transport). Do not move past M1 until both Claude Desktop and Claude Code successfully discover all (then-implemented) tools.

---

### Pitfall 12: Schema endpoints leaking foreign-key column names

**What goes wrong:**
`describe_table(database, table)` is supposed to strip hidden columns. But what about the response shape? Datasette's schema response often includes `foreign_keys: [{column, other_table, other_column}]` arrays. Even if the FK column itself is in `HIDDEN_COLUMNS`, the `other_table` reference can name a hidden table — leaking its existence and the column it joins on.

A second leak: Datasette includes index definitions, FTS auxiliary table references, and `sqlite_master` introspection. If we naively forward the JSON, all of that surfaces.

**How to avoid:**
- `describe_table` rebuilds the schema response from scratch — only columns (post-strip), types, nullability, primary-keyness (without revealing the actual PK column name if it's hidden), and the explicit `light` vs full distinction the PRD requires.
- Never include `foreign_keys`, `indexes`, `triggers`, `auxiliary tables` from Datasette's schema endpoint.
- Test: feed the full Datasette schema for `judgments_fragments` through `describe_table`; assert response keys are exactly `{name, columns, light_columns, row_count, description}` (or whatever we standardize on) with no leakage of `id`, `judgment_id`, or FK metadata.

**Warning signs:**
- `describe_table` response size proportional to upstream schema response size.
- `git grep -n 'foreign_keys\|indexes' src/` finds these terms outside test fixtures.

**Phase to address:** M2 (Discovery surface).

---

### Pitfall 13: Structured logs that themselves leak data

**What goes wrong:**
The PRD's observability requirement says "tool, db, table, duration, status, IP-prefix." A diligent implementer adds "filters" or "row count" or "first result preview" for debugging. Then prod logs contain full filter `value` strings (potentially hostile, per Pitfall 4) and row content. If logs go to a third-party aggregator, this:
- Re-exposes user-supplied prompt-injection text to whoever reads logs.
- For row content: re-exposes "hidden" column values that we stripped from the *response* but logged for "debug" purposes.

**How to avoid:**
- Lock the log schema in `config.py`: a fixed set of field names. Anything else is a CI lint failure.
- Filter values logged as their *type and length* only: `filters=[{column: "title", op: "contains", value: "<str:42>"}]`.
- Never log row contents, ever. Counts only.
- `/healthz` and structured logs must not include database names that are hidden. Apply the same denylist on the log side as on the response side.
- Operator runbook: log retention ≤ 30 days, no third-party aggregator without an explicit decision.

**Warning signs:**
- Any log line whose length varies meaningfully with input value length.
- Logs from a `query_table` call with a 5 KB filter value end up multi-KB lines.

**Phase to address:** M7 (Rate limiting and errors / logging). Validated in M8 (soak).

---

### Pitfall 14: `httpx.AsyncClient` lifecycle and pool exhaustion

**What goes wrong:**
A common production failure with `httpx.AsyncClient`: after 3–12 hours, one or more workers' clients start throwing `PoolTimeout` on every request, even for fresh requests. Causes: long-lived clients with cancelled tasks not releasing connections, upstream silently dropping idle keepalive sockets without the client noticing, and (in our case) the rate limiter rejecting work mid-request without freeing the upstream connection.

A second failure: instantiating a new `AsyncClient` per request "to be safe" — kills throughput, exhausts ephemeral ports under load, and disables connection reuse for upstream.

**How to avoid:**
- Single `AsyncClient` for the process lifetime, created at startup, closed at shutdown.
- Set `limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)` explicitly and tune to match upstream's capacity.
- Set `timeout=httpx.Timeout(connect=5, read=15, write=5, pool=10)` explicitly; never use the default which is no-timeout-after-connect.
- On any `PoolTimeout` exception, retry once with a fresh client (swap the global). Log the swap as a structured event.
- On cancellation: ensure the upstream request is properly awaited or closed; `try/finally` around upstream calls.
- Soak test (24h) must verify no PoolTimeouts and stable connection count.

**Warning signs:**
- p95 latency stable for hours, then suddenly all requests time out.
- `lsof` on the process shows growing CLOSE_WAIT / TIME_WAIT counts.
- Memory drifts upward at a steady rate over hours.

**Phase to address:** M1 (set the client up correctly at the start); validated in M8 (soak test).

---

### Pitfall 15: `claude-for-legal` submission — preventable rejection causes

**What goes wrong:**
Based on `CONNECTORS.md` requirements and Anthropic's general directory submission rules, PRs to `claude-for-legal` are rejected or stalled when:

1. **No public docs link**: README in our own repo isn't enough; the directory expects a stable URL covering tools, auth, data coverage.
2. **No privacy policy**: even though we're read-only and anonymous, the directory needs a privacy statement (what we log, how long, third-party sharing). Missing → immediate rejection per directory rules.
3. **Tool descriptions don't make use cases obvious**: reviewers skim. "Returns rows from a Datasette table" loses to "Search Singapore court judgments by date, court, and party."
4. **Heavy dependency footprint**: a `pyproject.toml` with 40 deps invites scrutiny. Our PRD constrains this; don't drift.
5. **No test suite or no integration test against the real upstream**: reviewers verify the connector works end-to-end. Gated live tests are good, but they must actually run somewhere (CI on a schedule, or a `make verify` target the reviewer can run).
6. **`.mcp.json` entry doesn't match the plugin's existing format**: spurious fields, missing tagline, wrong key casing.
7. **No injection-resistance demonstration**: CONNECTORS.md explicitly calls out "retrieval-quality and injection-resistance checks." Include a section in the README showing how envelope labeling and the trailing sentence interact.
8. **Practice-area fit not articulated**: PR opens against `claude-for-legal` without saying *which* plugins benefit, leaving the reviewer to guess.
9. **Scope creep at submission**: introducing speculative features (write tools, auth tiers) in the same PR. Keep the surface small and proven.

**How to avoid:**
- Publish docs at `mcp.zeeker.sg/docs` (or a GitHub Pages site) before opening the PR. Include: tools, parameters, error catalog, rate limits, provenance shape, privacy policy.
- Submission checklist in `.planning/`: docs URL ✓, privacy policy ✓, README in connector repo ✓, live tests passing ✓, `.mcp.json` formatted to match plugin's existing entries ✓, three concrete LLM use cases ✓.
- Look at *actually merged* `.mcp.json` entries in `claude-for-legal` plugins; mimic their structure character-for-character.
- Tool descriptions in `.mcp.json` and in tool registration must be identical and use-case-driven.
- Submit to one plugin first (recommend `regulatory-legal` per PRD context section) with an explicit one-paragraph rationale tying our four databases to that plugin's stated purpose.

**Warning signs:**
- PR sits open > 7 days with no reviewer comment → docs/scope is unclear.
- Reviewer comments asking "what does this do that X doesn't" → use-case framing failed.
- Reviewer asks for live demo or recording → testing story was weak.

**Phase to address:** M9 (Submission), but preconditions span M6 (envelope/safety, for the injection-resistance writeup) and M8 (tests passing for the testing story).

---

## Moderate Pitfalls

### Pitfall 16: `_extras` / `_shape` Datasette parameters drift between versions

**What goes wrong:**
Datasette's JSON API has evolved through 0.x and 1.0a versions. The `?_shape=` parameter, the `?_extras=` parameter, the structure of pagination metadata, and even the rank/relevance column name in FTS have all shifted. Pinning to a specific upstream behavior without verifying `data.zeeker.sg`'s exact Datasette version means our integration breaks on their next upgrade.

**How to avoid:**
- Pin our integration tests to actual response fixtures captured from `data.zeeker.sg` at a known date. Re-capture and diff before any release.
- Document the Datasette version we're targeting in `config.py` (`UPSTREAM_DATASETTE_VERSION = "1.0a..."`).
- Have a smoke test that hits `data.zeeker.sg/-/versions.json` and warns if the version drifts.

**Phase to address:** M3 onward — integration tests must capture real responses.

---

### Pitfall 17: 5xx retry policy too eager

**What goes wrong:**
PRD says "upstream 5xx: retry once with backoff." Easy to interpret as "retry every 5xx including 504." If upstream is timing-out under load, retrying multiplies the load and prolongs the outage. Also: retrying POST-equivalent operations (we have none, but if a future write tool gets added, this becomes critical) risks duplicate side-effects.

**How to avoid:**
- Retry only 502 and 503, not 504. A 504 means upstream took too long; retrying gives it more work.
- Cap retries at 1 (PRD-compliant); use exponential backoff with jitter (e.g., 250ms + uniform(0, 250ms)).
- Track retry rate as a metric — sustained > 5% retry rate is a runbook trigger.

**Phase to address:** M7.

---

### Pitfall 18: Default `databases` in `search` makes scope creep silent

**What goes wrong:**
PRD's open question: "should `search` default to all four databases?" If yes, adding a fifth database later silently expands every existing caller's scope. If the fifth has different licensing or different sensitivity, callers may not notice.

**How to avoid:**
- Default `databases` to the *explicit current four-name list*, encoded in `config.py`. Adding a fifth database requires updating the default — making it a visible decision in PR review.
- Tool description names the four databases explicitly.

**Phase to address:** M4 (Search).

---

### Pitfall 19: Provenance `retrieved_at` clock skew between requests in one tool call

**What goes wrong:**
A `query_table` call that performs multiple upstream requests (fragment join: lookup parent, then fragment rows) records `retrieved_at` for the envelope — which timestamp? If you take the *last* request's timestamp, you under-state the data's freshness if there's any caching. If you take the *first*, you under-state for the same reason in the other direction.

**How to avoid:**
- `retrieved_at` = timestamp at the start of *our* tool invocation (request received). Document this in the envelope schema. It's the time we *asked* upstream, not the time we got the answer.

**Phase to address:** M6 (Envelope).

---

### Pitfall 20: `fetch` URL normalization mismatches

**What goes wrong:**
A user calls `fetch(url="https://www.singaporelawwatch.sg/Headlines/foo/")` but Datasette has stored the URL as `https://singaporelawwatch.sg/Headlines/foo` (no `www`, no trailing slash). Result: `not_found`, despite the row existing.

**How to avoid:**
- Document URL-match semantics: exact string equality. Document examples in the tool description. Do NOT silently normalize — silent normalization breaks downstream tooling that expects identity preservation.
- Provide a `search` path as the recommended fallback when `fetch` returns `not_found`.

**Phase to address:** M3.

---

## Minor Pitfalls

### Pitfall 21: HTTP/2 vs HTTP/1.1 with Uvicorn

Uvicorn doesn't natively support HTTP/2 (would need `hypercorn` or a fronting proxy). If TLS termination upgrades to HTTP/2 to the client but downgrades to HTTP/1.1 to Uvicorn, that's fine — but mismatched expectations about streaming (e.g., assuming HTTP/2 multiplexing) will fail. Document: HTTP/1.1 keep-alive is what Uvicorn provides; multiple concurrent MCP requests over one TCP connection are *not* supported without HTTP/2 at the edge.

**Phase to address:** M1 (transport documentation).

---

### Pitfall 22: Single-process concurrency saturation

PRD's "50 concurrent requests in single process." Python async + httpx can handle this comfortably, but a CPU-bound serialization step (rendering large `retrieved_content` responses with `json.dumps`) blocks the event loop. Use `orjson` or chunk large responses; profile under load.

**Phase to address:** M8 (soak).

---

### Pitfall 23: License field in envelope hardcoded to CC-BY-4.0

PRD's envelope template literally says `"license": "CC-BY-4.0"`. Not every Zeeker dataset is necessarily CC-BY-4.0 — `sg-gov-newsrooms` content may be Singapore government works (different licensing). Verify per-database, encode in `config.py`, and key the envelope by source database. Wrong-license attribution in citations is reputationally bad.

**Phase to address:** M6 — before envelope ships, audit the four databases' actual licenses.

---

### Pitfall 24: `/healthz` reveals upstream status

If `/healthz` does a live ping of `data.zeeker.sg` and exposes the result, it becomes a free upstream-status probe — also a way to indirectly enumerate which IPs we connect to (if response time varies). Make `/healthz` purely a process-liveness check; have a separate authenticated path (or no path at all) for upstream-health diagnostics.

**Phase to address:** M7.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip cursor binding (`qhash`) — just passthrough `_next` | One less hash to compute | Silent wrong-result bugs when callers vary sort/filters across pages | Never for production |
| Echo raw filter values in error messages for "developer ergonomics" | Easier dev debugging | Prompt-injection channel outside envelope | Behind a `DEBUG=1` env flag, never in prod |
| Use a single global `dict` for the rate-limit bucket store with no size cap | Simplicity | Memory DoS via XFF spoofing | Never — always cap |
| Hardcode license string in envelope | One less config field | Wrong attribution propagating into LLM citations | Never for the four-database setup |
| Pass FTS query through unescaped to support advanced search | "Power user" syntax works | Syntax errors become opaque upstream failures; hidden-column probe surface | Only with an explicit parser-based operator subset |
| Include `foreign_keys` in `describe_table` for completeness | Easier introspection for power users | Leaks hidden-table relationships | Never |
| Defer `/healthz` to "ping upstream and reflect status" | Free upstream monitoring | Side-channel for status probing; conflates process health with upstream health | Behind auth + on a separate path |
| Run all live tests on every push | Fast feedback | Hammers upstream → looks like an attacker | Gated behind env flag, run on schedule, with rate-limit-friendly delays |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Datasette `/-/search.json` | Default to all databases; trust returned `database/table` fields | Pass `?database=` filter; post-strip; whitelist of allowed (db, table) pairs |
| Datasette pagination | Trust `next` is present whenever more rows exist | Always check `truncated` too; treat truncated-without-next as a server-side error to surface |
| Datasette FTS | Pass user query raw | Double-quote-wrap and escape internal quotes; map FTS syntax errors to `invalid_query` |
| Datasette schema endpoint | Forward as-is via `describe_table` | Rebuild from a strict allow-list of fields |
| Reverse proxy (operator-managed) | Trust XFF blindly; assume operator strips incoming XFF | Configurable proxy-depth; document operator contract; cap bucket store; fallback to socket peer when XFF missing |
| Claude Code MCP client | Use `anyOf`/`oneOf` at schema root | Flat `type:"object"` schemas, discriminator-string parameters |
| Claude Desktop MCP client | Assume HTTP-only; ignore SSE fallback | Implement both POST and GET on a single endpoint |
| FastMCP error returns | Raise Python exceptions, let framework serialize | Custom error class with stable `code` field; map every error catalog entry through it |
| `claude-for-legal` `.mcp.json` | Invent your own JSON shape | Copy an existing merged entry character-for-character |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| New `AsyncClient` per request | High latency on cold requests; ephemeral port exhaustion | Single global client | At ~100 req/s sustained |
| Unbounded rate-limit bucket store | Memory creeping up; OOM after hours | LRU cap + TTL eviction | When attacker rotates XFF or under organic high-cardinality traffic (~10k+ unique IPs/day) |
| `json.dumps` on large `retrieved_content` blocking event loop | p95 spikes correlated with large responses | `orjson` or chunked serialization | When a single response is > 100 KB |
| Synchronous fragment-join lookup (parent fetch then fragment fetch sequentially) | 2× latency for fragment queries | Acceptable for v1 (the two queries can't easily be parallelized given the dependency) | n/a — accept the latency |
| Synchronized 429 retries (no jitter) | Sawtooth traffic pattern in logs | Document jitter in tool description; possibly set `Retry-After` to a randomized value | At ~10+ concurrent rate-limited clients |
| Logging row content for debugging | Log volume balloons; PII/hostile content in logs | Strict log schema enforced by CI | Immediately in prod |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Distinct error messages for "hidden" vs "unknown" table | Enumeration of hidden tables via probe | Unify all such errors to `unknown_table` with identical message |
| Echoing user-supplied filter values in errors / logs | Prompt-injection channel outside envelope | Echo only column names + types; reference values positionally |
| Trusting first XFF entry | Rate-limit bypass + memory DoS | Trust only rightmost (after stripping known proxy hops); cap bucket store |
| Forwarding Datasette's `foreign_keys` in `describe_table` | Leaks hidden-table relationships | Rebuild schema response from allowlist |
| Allowing FTS user input to reach Datasette unescaped | Possible column-targeted search of hidden FTS columns; opaque syntax errors | Quote-escape input; restrict to phrase search in v1 |
| `/healthz` pings upstream | Free upstream-status probe for attackers | Process-liveness only |
| Heavy text inlined at row top level on a new tool | Breaks envelope-labeling injection-resistance contract | `EnvelopeBuilder` is the only emission path; CI lint forbids alternatives |
| Logging full request payload | Hostile filter values persisted | Schema-validated log format |
| No `Origin` header check | Browser-based CSRF against the MCP endpoint | Origin allowlist; reject unknown origins on the streamable HTTP endpoint |

---

## UX Pitfalls (Caller / LLM Experience)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Tool description doesn't name the four databases | LLM doesn't know what's available; wastes `list_databases` calls every session | Name the databases in `list_databases` and reference them in cross-cutting tool descriptions |
| Cursor errors are vague (`invalid_cursor`) | LLM retries with the same bad cursor | Error data includes whether mismatch is filter/sort/columns; suggests starting fresh |
| `not_found` from `fetch` has no recovery hint | LLM doesn't know to try `search` | Error message: "URL did not match any indexed record. Try `search` with the document title." |
| `query_table` returns 0 results for valid filter on a misspelled column | Looks like data is missing | Validate columns against schema; return `unknown_column` not empty result set |
| Heavy column requested but not in light set — error | Caller has to retry | Just include it in `retrieved_content` and proceed; only error on hidden columns |
| Different tool descriptions don't all end with the trailing sentence | Inconsistent injection-resistance signal | CI check: every tool description ends with `TOOL_TRAILER` |

---

## "Looks Done But Isn't" Checklist

- [ ] **Envelope:** Heavy columns absent from top-level row keys — verify with snapshot test across all tools.
- [ ] **Envelope:** Every tool description ends with the exact trailing sentence — CI assertion against `TOOL_TRAILER` constant.
- [ ] **Hidden-table enforcement:** `unknown_table` error identical for hidden and nonexistent tables (string match, not just code match).
- [ ] **Hidden-column enforcement:** `describe_table` response does not contain `id`, `judgment_id`, or any FK column for any table — fixture-based test.
- [ ] **Cursor:** Same cursor with different `sort` or `filters` returns `invalid_cursor`, not silently wrong rows.
- [ ] **Truncation:** A synthetic 1,500-fragment parent paginates fully without losing rows.
- [ ] **Rate limit:** Crafted XFF spoof from one TCP peer hits the same bucket; from different peers, different buckets (with `TRUSTED_PROXY_DEPTH=1`).
- [ ] **Rate limit:** Bucket store size bounded under 10k spoofed XFF values.
- [ ] **Error messages:** No filter `value` text appears in any error or log line for hostile-input test corpus.
- [ ] **FTS:** Search query containing `"`, `(`, `*`, `OR`, `:` works (returns phrase results or empty, not a 500).
- [ ] **Schema:** Tool input schemas contain no top-level `anyOf` / `oneOf` / `allOf`; validate against MCP 2025-06-18 spec.
- [ ] **Transport:** Both Claude Desktop and Claude Code complete a full tool-call round-trip in CI / dev verification.
- [ ] **Logs:** Log line length bounded regardless of filter value size.
- [ ] **`/healthz`:** Returns 200 without consulting upstream.
- [ ] **`.mcp.json` entry:** Formatted identically to an existing merged plugin entry; tagline ≤ 80 chars; description ≤ 200 chars.
- [ ] **Privacy policy:** Published at a stable URL before PR opens.
- [ ] **Live tests:** Pass against `data.zeeker.sg` in a gated CI job within the last 7 days before submission.
- [ ] **Soak:** 24h soak run shows stable memory, no `PoolTimeout`, no log growth beyond expected.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Heavy text leaks at row top level (Pitfall 5) | LOW if caught pre-release; HIGH after submission | Patch EnvelopeBuilder; bump server version; redeploy; coordinate with directory if served bad responses for > 24h |
| Hidden-table title in search results (Pitfall 3) | MEDIUM | Hotfix the `database=` filter; force-strip; rebuild fixtures; verify with adversarial test set |
| XFF spoofing bypass detected (Pitfall 6) | MEDIUM | Update `TRUSTED_PROXY_DEPTH`; force bucket store flush; document the operator contract correction |
| `httpx` PoolTimeout in production (Pitfall 14) | LOW | Restart process (already configured swap-on-PoolTimeout should self-recover); investigate root cause from logs |
| `.mcp.json` PR rejected for missing privacy policy (Pitfall 15) | LOW | Publish policy at `mcp.zeeker.sg/privacy`; update PR with link; usually re-reviewed within days |
| `.mcp.json` PR rejected for scope concerns | MEDIUM | Trim PR to minimum surface; resubmit with explicit practice-area rationale and use cases |
| Datasette upstream version bump breaks our integration (Pitfall 16) | MEDIUM | Re-capture fixtures; diff schemas; update parsers; emergency release |
| Cursor mis-binding causing wrong rows shipped to LLM clients (Pitfall 1) | HIGH (data trust) | Add `qhash` binding; force-invalidate all in-flight cursors via server restart; communicate to known integrators |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Opaque-cursor mis-binding | M3 | Cursor walk test with varying sort/filters |
| 2. Datasette 1k-row silent truncation | M5 | 1,500-fragment synthetic parent paginates fully |
| 3. `/-/search.json` leaks hidden tables | M2 + M4 | Adversarial search-result audit; error-string parity test |
| 4. Echoed filter values as injection vector | M3 (continuing M6) | Hostile-input corpus test against error/log surfaces |
| 5. Heavy text inlined at row top level | M6 | EnvelopeBuilder snapshot tests; CI lint on response paths |
| 6. XFF blind trust | M7 | Spoofed-XFF tests; bucket store size cap; operator contract documented |
| 7. 429 retry storms | M7 | Concurrent-retry simulation; Retry-After semantics test |
| 8. Fragment-parent join ambiguities | M5 | Deterministic-order tests; multi-match parent fixture |
| 9. FTS user-input escaping | M4 | Special-character query test |
| 10. JSON-RPC error shape / Claude Code strict schema | M1 (onward) | Schema linter; live tool-list verification in both Desktop and Code |
| 11. Streamable HTTP / SSE negotiation | M1 | Both clients complete a full session in dev |
| 12. Schema endpoint FK leakage | M2 | `describe_table` field whitelist test |
| 13. Logs leaking data | M7 | Log-line length test under hostile inputs |
| 14. `httpx` pool lifecycle | M1 + M8 | 24h soak with stable connection metrics |
| 15. Submission rejection causes | M6 + M8 + M9 | Pre-submission checklist; docs URL live; live test recency |
| 16. Datasette version drift | M3+ | Fixture-versioning + `/-/versions.json` smoke check |
| 17. Over-eager 5xx retry | M7 | Retry rate as a metric; 504 not retried |
| 18. `search` default-databases scope creep | M4 | Explicit four-name list in config |
| 19. `retrieved_at` ambiguity | M6 | Documented semantics: start-of-tool-call |
| 20. URL normalization | M3 | Documented exact-match semantics |
| 21. HTTP/2 expectations | M1 | Transport doc |
| 22. Event-loop blocking on large responses | M8 | Profile under soak |
| 23. License hardcoded | M6 | Per-database license audit |
| 24. `/healthz` upstream probe | M7 | Process-liveness only test |

---

## Sources

- [MCP Specification 2025-06-18: Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) — schema requirements, annotation best practices.
- [MCP Specification 2025-03-26: Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP, SSE deprecation.
- [Why MCP Deprecated SSE and Went with Streamable HTTP (fka.dev)](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
- [Why MCP's Move Away from Server Sent Events Simplifies Security (auth0)](https://auth0.com/blog/mcp-streamable-http/) — Origin validation, session ID handling.
- [Claude Code strict MCP schema validation issue #10606](https://github.com/anthropics/claude-code/issues/10606) — anyOf/oneOf/allOf rejected at root.
- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification) — error response shape.
- [MCP Error Codes (mcpevals.io)](https://www.mcpevals.io/blog/mcp-error-codes)
- [Datasette JSON API documentation](https://docs.datasette.io/en/latest/json_api.html) — pagination, `_next`, `truncated`, `max_returned_rows`.
- [Datasette settings documentation](https://docs.datasette.io/en/stable/settings.html) — 1,000 row cap, query timeout.
- [Datasette full-text search documentation](https://docs.datasette.io/en/stable/full_text_search.html) — FTS5 column ordering, rank.
- [Escape your Full Text Search queries (haroldadmin)](https://blog.haroldadmin.com/posts/escape-fts-queries) — FTS5 quote-escaping technique.
- [SQLite User Forum: Escape punctuation in FTS queries](https://sqlite.org/forum/info/82344cab7c5806980b287ce008975c6585d510e95ac7199de398ff9051ae0907)
- [Don't trust the first item in the X-Forwarded-For header (Mark Amery)](https://markamery.com/blog/dont-trust-the-first-item-in-the-x-forwarded-for-header/) — XFF parse-from-right pattern.
- [The perils of the "real" client IP (adam-p)](https://adam-p.ca/blog/2022/03/x-forwarded-for/)
- [GHSA-hm36-ffrh-c77c: X-Forwarded-For spoofing bypasses Litestar rate limiting](https://github.com/litestar-org/litestar/security/advisories/GHSA-hm36-ffrh-c77c)
- [Protecting against indirect prompt injection in MCP (Microsoft)](https://developer.microsoft.com/blog/protecting-against-indirect-injection-attacks-mcp)
- [MCP Security Notification: Tool Poisoning Attacks (Invariant Labs)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- [Indirect Prompt Injection in MCP Tools (StackOne)](https://www.stackone.com/blog/prompt-injection-mcp-10-examples/)
- [MCP Tools: Attack Vectors and Defenses (Elastic Security Labs)](https://www.elastic.co/security-labs/mcp-tools-attack-defense-recommendations)
- [Rate Limiting Strategies (caduh.com)](https://www.caduh.com/blog/rate-limiting-strategies) — clock skew, Retry-After semantics.
- [HTTP Headers: Retry-After Practical Patterns (TheLinuxCode)](https://thelinuxcode.com/http-headers-retry-after-practical-patterns-pitfalls-and-production-ready-use/)
- [httpx Resource Limits documentation](https://www.python-httpx.org/advanced/resource-limits/)
- [httpx Timeouts documentation](https://www.python-httpx.org/advanced/timeouts/)
- [httpx Issue #2556: PoolTimeout total failure during AsyncClient reuse](https://github.com/encode/httpx/discussions/2556)
- [httpx Issue #1461: Pool connection not closed on cancel](https://github.com/encode/httpx/issues/1461)
- [Uvicorn Issue #1564: Memory leak when using request.state](https://github.com/Kludex/uvicorn/issues/1564)
- [anthropics/claude-for-legal — CONNECTORS.md](https://github.com/anthropics/claude-for-legal/blob/main/CONNECTORS.md) — primary submission-requirements source.
- [Submitting to the Connectors Directory (Anthropic docs)](https://claude.com/docs/connectors/building/submission)
- [Remote MCP Server Submission Guide (Anthropic Help Center)](https://support.claude.com/en/articles/12922490-remote-mcp-server-submission-guide)
- [Anthropic Goes All-In on Legal — context on the connector directory and plugin set](https://www.lawnext.com/2026/05/anthropic-goes-all-in-on-legal-releasing-more-than-20-connectors-and-12-practice-area-plugins-for-claude.html)

---
*Pitfalls research for: Zeeker MCP Connector (mcp.zeeker.sg → data.zeeker.sg)*
*Researched: 2026-05-13*
