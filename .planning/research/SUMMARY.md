# Project Research Summary

**Project:** Zeeker MCP Connector (`mcp.zeeker.sg`)
**Domain:** Remote MCP server — read-only translator from `data.zeeker.sg` (Datasette, Singapore legal datasets) to MCP-compatible LLM clients, primarily Claude via the `anthropics/claude-for-legal` plugin suite
**Researched:** 2026-05-13
**Confidence:** HIGH on stack / architecture; MEDIUM on submission specifics; HIGH on the pitfall surface

## Executive Summary

Zeeker MCP is a thin, stateless, single-process Python translator: streamable HTTP MCP in, Datasette JSON out, with a fixed provenance envelope, hidden-data stripping, an in-memory IP-keyed token bucket, and a fixed trailing safety sentence in every tool description. The four research streams converged on the architecture the PRD describes — they did **not** suggest re-shaping it. Where they pushed back, they pushed on *details*: cursor binding (Pitfall 1), upstream truncation handling (Pitfall 2), echoed-filter-value injection vectors (Pitfall 4), XFF blind trust (Pitfall 6), `describe_table` FK leakage (Pitfall 12), and Claude Code's strict input-schema validation (Pitfall 10). All of these belong in specific milestones already on the PRD timeline.

The recommended stack locks in cleanly: **FastMCP 3.2.4** (standalone, not the mirror inside `mcp` 1.27) on Starlette 1.0.0 / Uvicorn 0.46.0, with a single long-lived `httpx.AsyncClient` 0.28.1, Pydantic 2.13.4 for I/O models, and `structlog` 25.5.0 for the PRD's structured-JSON observability target. Six runtime deps + four dev deps. `ruff` replaces `black`. The rate-limit story uses an ASGI-level token bucket implementing FastMCP's `RateLimitingMiddleware` math plus ~40 LOC of custom code for the 24h ceiling — no `pyrate-limiter` / `throttled-py` / `stamina` needed. Single Uvicorn worker is non-negotiable for v1 because the in-memory bucket is per-process.

The biggest risks are not technical surprises but **discipline failures**: a new tool slipped in that bypasses the envelope (Pitfall 5), an "ergonomic" error message that echoes a hostile filter value (Pitfall 4), a `describe_table` response that forwards Datasette's `foreign_keys` array (Pitfall 12), a cursor passed through without binding to the request shape (Pitfall 1), or a registry PR that opens without a privacy policy and three concrete use cases (Pitfall 15). Mitigation is structural: an `EnvelopeBuilder` that is the *only* response-emission path, a CI lint that no tool returns raw dicts, a snapshot-test suite per tool, and a `qhash`-bound cursor. M1 must additionally include tool annotations (`readOnlyHint`, `idempotentHint`, `openWorldHint`), a request-ID echoed in error envelopes, an upstream check exposed only on an operator-private path (NOT public `/healthz`), and a flat-`type:object` schema constraint to keep Claude Code's strict validator happy — these are PRD additions surfaced by the research that need to land in the roadmap.

## Key Findings

### Recommended Stack (Locked Decisions)

| Component | Pin | Why |
|---|---|---|
| **`fastmcp`** | `~=3.2` (3.2.4) | Standalone PrefectHQ distribution; tracks the current MCP spec (2025-06-18). Do not use `mcp.server.fastmcp` from the `mcp` 1.27 SDK — older snapshot. |
| **`pydantic`** | `~=2.13` (2.13.4) | Tool input/output schemas. `model_config = {"extra": "forbid"}`; flat `type:object` schemas only (Pitfall 10). |
| **`httpx`** | `~=0.28` (0.28.1) | Single long-lived `AsyncClient` in lifespan. `Limits(max_connections=50, max_keepalive_connections=20, keepalive_expiry=30)`, explicit `Timeout(connect=3, read=5, write=5, pool=3)`. HTTP/1.1 (Datasette). |
| **`starlette`** | `>=0.41,<2` | FastMCP's `http_app()` returns a Starlette app; mount under our own parent for ASGI middleware. |
| **`uvicorn`** | `~=0.46` | **Single worker only.** Multi-worker silently breaks in-memory rate limiter. `--proxy-headers` + `--forwarded-allow-ips` set to proxy CIDR. |
| **`structlog`** | `~=25.5` | `contextvars.bind_contextvars` for request-scoped tool/db/table/request_id propagation. |
| **`uv`** | `~=0.11` | `uv sync --frozen` in production images. |
| **`ruff`** | `~=0.15` | Replaces Black + isort + most pyupgrade rules. Byte-identical to Black. |
| **`pytest` + `pytest-asyncio` + `pytest-httpx`** | `~=8.3` / `~=1.3` / `~=0.36` | Test runner + async + `httpx_mock` for upstream stubs. |
| **Python** | `>=3.12` | Floor for `taskgroup`. |

**Explicitly avoided:** `requests` (sync), `aiohttp` (older API), FastAPI (dead weight over Starlette), `python-json-logger` alone (no async context propagation), `tenacity` direct, `gunicorn` workers (breaks rate-limit math), `pyrate-limiter`/`throttled-py` (FastMCP bucket math + ~40 LOC daily cap suffices), `mcp` SDK as primary import, `black` alongside `ruff format`, Pydantic v1, `mypy strict` in v1.

### Expected Features

The submission contract Zeeker is held to is **not** "fits a wishlist slot" — `claude-for-legal/CONNECTORS.md` is a tool-category placeholder taxonomy. The de-facto contract is the **citation-verification contract**: every citation a plugin emits must be tagged with a connector source or marked `[verify]`. Zeeker earns trust by producing citation-ready, source-tagged output.

**Table stakes (v1 must-have):**
- Six MCP tools (`list_databases`, `list_tables`, `describe_table`, `search`, `query_table`, `fetch`) with predictable shapes
- Provenance envelope on every success (source, db, table, retrieved_at, license, attribution, citation synthesis fallback)
- URL/ID as universal addressing scheme
- Hidden-data enforcement on both edges (request rejection + response stripping)
- Light-vs-heavy column model; heavy text only under `retrieved_content`
- Predictable enumerated error codes with recovery hints (`retry_after_seconds`, valid-column lists)
- Tool descriptions that fit context budget: 1–2 sentences + trailing safety sentence
- Injection-resistance via labeling, not filtering
- Cursor-based pagination (opaque to caller, **bound to request shape** — Pitfall 1)
- `/healthz` (liveness only) + structured JSON logs (request_id, tool, db, table, duration, status, IP-prefix)
- Rate-limit semantics surfaced in tool descriptions so the LLM knows 429 is recoverable
- Schema-validated input on every tool (flat `type:object`, no top-level `anyOf`/`oneOf`/`allOf`)
- Bounded default response sizes
- TLS + reachability from Anthropic IP ranges (operator concern; document in README)
- Streamable HTTP transport with SSE fallback per spec

**PRD additions surfaced by research (not in PRD §17, must land in roadmap):**
- **Tool annotations** (`readOnlyHint: true`, `idempotentHint: true`, `openWorldHint: true`) on every tool — required for Claude to auto-approve calls in the agent loop. **Land in M1 with the first tool.**
- **Request ID echoed in error envelopes** — operators need this for incident response.
- **Upstream check exposed on an operator-private path, NOT public `/healthz`.**
- **Explicit `available_columns` shape in `describe_table` response** — `{name, columns, light_columns, available_columns, url_keyed, supports_fragments, row_count, description}`. No `foreign_keys`, no `indexes`, no `triggers` (Pitfall 12).
- **Documented Anthropic IP-allowlist requirement** in deployment README.

**Differentiators worth keeping:**
- Transparent fragment-parent join via URL filter (genuinely novel among public MCP connectors)
- Citation synthesis where no native citation field exists (for PDPC)
- Stateless, no-mirror design
- Cross-database `search` with hidden-table post-filter (default to the four-name list explicitly per Pitfall 18)
- Per-table URL-column mapping hidden from the LLM
- License/attribution baked per-response and **per-database** (Pitfall 23)
- Filter operator set tuned for legal use; document `contains` case-sensitivity

**Anti-features (deliberately excluded):**
Raw SQL / `execute_sql`; write tools; content scrubbing / lexical filtering; auth-required-in-v1; persistent caching that diverges from upstream; v1 aggregation tools; subscription / push; `/status` mirror; "describe everything" mega-tool; hidden-table "debug" exposure; polymorphic return shapes; `fetch_text(url)` shortcut; verbose multi-paragraph tool descriptions.

### Architecture Approach

**Two-tier middleware** layered over a flat tool surface, denylist enforcement at both edges, fragment-join orchestration in the tool layer (not the HTTP client), and `ToolError`-driven error translation at a single seam.

```
src/mcp_zeeker/
├── app.py                # build_app(): Starlette parent + ASGI middleware stack
├── server.py             # FastMCP instance, @tool registration, custom_route("/healthz")
├── config.py             # ALL denylists / mappings / limits — single source of truth
├── schema.py             # Pydantic: Filter, QueryTableInput, Envelope, Provenance
├── errors.py             # ErrorCode, ToolError, upstream→tool mapping
├── observability.py      # structured logger + contextvars
├── tools/                # one module per tool (6 modules)
├── upstream/             # client.py, urls.py, filters.py, responses.py — denylist-blind
└── middleware/           # ASGI: ratelimit, logging | FastMCP: envelope, hidden, label
```

**ASGI middleware order (outermost → innermost):** `AccessLog` → `ErrorTranslation` (backstop) → `RateLimit`. 429s reject *before* FastMCP parses JSON-RPC but are still logged with `request_id`.

**FastMCP middleware order:** `ErrorTranslation` → `Envelope` → `HiddenData` → handler. On the way back, `HiddenData` runs before `Envelope` (operates on raw payload with `db`/`table` keys).

**Six tool modules, not 26.** Per-table policy lives in `config.py`. Adding a 27th table = config-only change.

### Critical Pitfalls (top 5, each owned by a milestone)

1. **Pitfall 1 — Cursor that isn't actually opaque (M3).** Datasette's `_next` is sort-order-sensitive; reusing across changed `sort`/`filters` silently returns wrong rows. **Mitigation:** cursor = `base64(json({"next": _next, "qhash": sha256(normalized_request)}))`. Reject mismatches with `invalid_cursor`. Property test the cursor walk.
2. **Pitfall 2 — Datasette's silent 1,000-row truncation (M5).** `max_returned_rows = 1000`. A 1,200-fragment judgment loses paragraphs 1,001+ with no `next` cursor. **Mitigation:** always read `truncated`; surface as `pagination.truncated`. For fragment joins, paginate by `(parent_fk, order_by)` with own LIMIT < 1,000. Regression test with synthetic 1,500-fragment parent.
3. **Pitfall 4 — Echoed filter values become injection vectors (M3, reinforced M6).** A hostile filter value echoed in an error message defeats envelope labeling. **Mitigation:** never echo user-supplied string values in errors or logs. Reference positionally. Log values as type+length.
4. **Pitfall 6 — XFF trusted blindly → rate-limit bypass + memory DoS (M7).** Naïve XFF parsing lets attackers spoof a fresh IP per request AND exhaust the bucket store. **Mitigation:** configurable `TRUSTED_PROXY_DEPTH` (default 1), parse right-to-left, LRU-cap bucket store (≤100k keys). Operator contract: proxy MUST overwrite XFF.
5. **Pitfall 10 — Claude Code's strict input-schema validation (M1, enforced onward).** Top-level `anyOf`/`oneOf`/`allOf` silently rejected by Claude Code v2.0.21+. Connector "works in Claude Desktop" and fails in the registry's primary client. **Mitigation:** flat `type: "object"` schemas. No top-level `Union` in Pydantic. CI check.

**Honorable mentions:**
- **Pitfall 5 — Heavy text inlined on a new tool (M6).** `EnvelopeBuilder` = only emission path; CI lint forbids alternatives.
- **Pitfall 12 — `describe_table` FK leakage (M2).** Rebuild schema response from allow-list.
- **Pitfall 15 — Submission preventable rejections (M9).** Pre-submission checklist (privacy policy, docs URL, mimic existing `.mcp.json`, 3 use cases, injection-resistance writeup, live tests recency).

## Implications for Roadmap

The PRD's 9 milestones (M1–M9) survive research review without restructuring. **M1 = `list_databases`** because it's the smallest tool that retires the most unknowns (transport, DNS, reachability, envelope shape) without dragging in filter, search, or fragment complexity.

### Phase 1: M1 — Skeleton transport + `list_databases`
**Rationale:** Smallest tool that exercises every layer end-to-end.
**Delivers:** `pyproject.toml`, `config.py` scaffold, `DatasetteClient`, `list_databases` over MCP, single-tool `EnvelopeBuilder` stub, `/healthz` (liveness).
**Research additions:**
- Tool annotations (`readOnlyHint`, `idempotentHint`, `openWorldHint`) — Pitfall 10 / Features
- Flat `type: "object"` input schemas — Pitfall 10
- `httpx.AsyncClient` lifecycle done right (single global, `Limits`, `Timeout`) — Pitfall 14
- Streamable HTTP at `/mcp` supporting POST + GET; `Mcp-Session-Id` honored; `Origin` allowlist — Pitfall 11
- Verify with **both** Claude Desktop and Claude Code — must succeed in both

### Phase 2: M2 — Discovery surface + denylists
**Delivers:** `list_tables`, `describe_table` with hidden-table 404s + hidden-column stripping. Populates `config.HIDDEN_TABLES` / `HIDDEN_COLUMNS`.
**Research additions:**
- Rebuild schema response from allow-list — no `foreign_keys`, no `indexes` — Pitfall 12
- Response shape: `{name, columns, light_columns, available_columns, url_keyed, supports_fragments, row_count, description}`
- Unify error messages and timing path: hidden-table and nonexistent-table both return identical `unknown_table` — Pitfall 3

### Phase 3: M3 — Structured retrieval (`query_table` + `fetch` non-fragment)
**Rationale:** Biggest "is upstream actually shaped like we think." Filter compiler highest-risk pure-logic module.
**Delivers:** 11 filter operators, cursor pagination, `columns` parameter validation, per-table URL-column mapping for `fetch`, light/heavy column model.
**Research additions:**
- **`qhash`-bound cursor** — Pitfall 1
- **No filter-value echo** in errors or logs from day one — Pitfall 4
- Document `fetch` URL-match: exact string equality, no silent normalization — Pitfall 20
- Document `contains` case-sensitivity in tool description
- Capture real Datasette fixtures from `data.zeeker.sg` for integration tests — Pitfall 16

### Phase 4: M4 — Search
**Delivers:** Cross-database FTS via `/-/search.json`, hidden-table post-strip, preview-only rows.
**Research additions:**
- Explicit `?database=` filter restricting to the four allowed databases — Pitfall 3
- Escape FTS user input: wrap in double quotes, double internal quotes — Pitfall 9
- Add `invalid_query` to error catalog — Pitfall 9
- Default `databases` = explicit four-name list in `config.py`, not "all" — Pitfall 18

### Phase 5: M5 — Fragments
**Rationale:** High-value, contained risk. Pure orchestration test.
**Delivers:** Transparent two-step parent-join for `*_fragments` tables.
**Research additions:**
- Read `truncated`; paginate by `(parent_fk, order_by)` with own LIMIT < 1,000 — Pitfall 2
- Deterministic parent tiebreaker: `ORDER BY updated_at DESC, id ASC LIMIT 1`. Log multi-match warnings — Pitfall 8
- Sort fragments by `(order_by, id)` with numeric coercion — Pitfall 8
- Regression test: synthetic 1,500-fragment parent paginates fully — Pitfall 2
- **Disproportionate test budget** (most complex orchestration; combined p50 ~600ms acceptable)

### Phase 6: M6 — Envelope hardening + injection labels
**Delivers:** Provenance envelope identical across all tools; citation synthesis; fixed safety sentence verified at registration time.
**Research additions:**
- **`EnvelopeBuilder.row(database, table, raw_row)` is the only emission path.** CI lint forbids handlers returning raw dicts — Pitfall 5
- `TOOL_TRAILER` constant + CI assertion every tool description ends with it — Pitfall 5
- Snapshot tests per tool: `set(row.keys()) ∩ HEAVY_COLUMNS == ∅`; `set(row["retrieved_content"].keys()) ⊆ HEAVY_COLUMNS`
- `retrieved_at` = start-of-tool-call timestamp — Pitfall 19
- **Per-database license audit** — encode in `config.py`; do not hardcode `CC-BY-4.0` — Pitfall 23
- Begin M9 preconditions: injection-resistance writeup — Pitfall 15

### Phase 7: M7 — Rate limiting + structured errors + `/healthz` + access logs
**Delivers:** Token bucket (burst 20 + sustained 1/s + daily 5k), `Retry-After`-correct 429s, 9-code error catalog, `/healthz` (liveness only), structured JSON logs.
**Research additions:**
- `TRUSTED_PROXY_DEPTH` configurable (default 1); XFF parse right-to-left; LRU-cap bucket store; TTL-evict idle buckets — Pitfall 6
- `Retry-After` = seconds to next single token (typically 1s) or seconds-to-rollover (daily). Integer seconds. `retry_after_seconds` in payload. Jitter advisory — Pitfall 7
- Retry only 502/503, not 504; one retry with 250ms + uniform(0, 250ms) jitter — Pitfall 17
- **Log schema locked in `config.py`** — fixed field set; filter values as type+length; never log row contents — Pitfalls 4 + 13
- **`/healthz` is liveness-only.** Upstream-health on operator-only path — Pitfall 24
- **Request ID echoed in error envelopes**

### Phase 8: M8 — Tests + 24h soak
**Delivers:** Coverage report, soak result (p95 < 1.5s, no PoolTimeouts, stable memory, log growth bounded).
**Research additions:**
- "Looks Done But Isn't" checklist (18 items in PITFALLS.md) is the M8 verification list
- Live integration tests gated by `ZEEKER_LIVE=1`; run nightly + pre-release
- Bucket store size cap verified under 10k spoofed XFF values — Pitfall 6
- HTTP/2 documentation (Uvicorn = HTTP/1.1 only) — Pitfall 21
- Event-loop blocking profile; add `orjson` only if justified — Pitfall 22

### Phase 9: M9 — Submission to `anthropics/claude-for-legal`
**Delivers:** PR with `.mcp.json` entry + README, targeting one plugin first (recommend `regulatory-legal`).
**Submission preconditions checklist:**
- Public docs at `mcp.zeeker.sg/docs` — Pitfall 15
- Privacy policy at stable URL — Pitfall 15
- `.mcp.json` formatted character-for-character against existing merged plugin entry — Pitfall 15
- Tool descriptions in `.mcp.json` = runtime registrations; use-case-driven — Pitfall 15
- Three concrete LLM use cases in README, tied to target plugin — Pitfall 15
- Injection-resistance writeup section — Pitfall 15
- Live tests passing within last 7 days — Pitfall 15
- Documented Anthropic IP-allowlist range
- No scope creep: no write tools, no auth tiers added in same PR

### Research Flags

**Phases likely needing `/gsd-research-phase` during planning:**
- **M3:** Filter compiler; Datasette JSON verification against real `data.zeeker.sg` fixtures; cursor binding semantics subtle.
- **M5:** Two-step orchestration, ordering tiebreakers, truncation handling, multi-match parents.
- **M7:** Token-bucket math (burst + sustained + daily simultaneously) + XFF parse-from-right + eviction policy.
- **M9:** Mimic existing merged `.mcp.json` character-for-character.

**Standard patterns (research-phase optional):** M1, M2, M4, M6, M8.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified within 24h against PyPI / Context7 / official docs. |
| Features | HIGH for MCP/OpenAI/Anthropic patterns; MEDIUM for `claude-for-legal` plugin-side citation guardrails; LOW for "regulatory primary source" wishlist (directory uses placeholders). |
| Architecture | HIGH for FastMCP middleware mechanics, Datasette JSON shape; MEDIUM for FastMCP issue #556 resolution status (anti-pattern guidance sound regardless). |
| Pitfalls | HIGH for MCP / JSON-RPC / Datasette / XFF; MEDIUM for `claude-for-legal` reviewer behavior. |

### Disagreements & Contradictions Resolved

1. **`/healthz` upstream check.** FEATURES.md wants an upstream ping; PITFALLS.md Pitfall 24 flags it as a side-channel. **Resolution:** `/healthz` liveness-only; upstream-health on a separate operator-only path.
2. **`search` default scope.** FEATURES.md wants "all four"; PITFALLS.md Pitfall 18 cautions about silent scope creep. **Resolution:** explicit four-name list in `config.py`.
3. **License field.** PRD says `CC-BY-4.0` constant; PITFALLS.md Pitfall 23 flags variation. **Resolution:** per-database license map in `config.py`, audited in M6.
4. **Black vs `ruff format`.** STACK.md recommends `ruff format`. **Resolution:** `ruff format` (byte-identical output). Update PRD note.
5. **Rate-limit middleware placement.** STACK.md suggests FastMCP's built-in; ARCHITECTURE.md says ASGI. **Resolution:** ASGI implementation so 429s never spend JSON-RPC parsing cost.

### Gaps to Address During Phase Planning

- Per-database license audit (M6)
- Datasette upstream version pin (M3) — hit `/-/versions.json`
- Target plugin selection for M9 (recommend `regulatory-legal`)
- `subject_tags` in `judgments` light columns (recommend YES)
- Anthropic IP allowlist range (M9)
- `Mcp-Session-Id` persistence under stateless mode (M1)
- XFF behavior under production reverse proxy (M1 smoke test)

## Sources

Primary (HIGH): Context7 `/prefecthq/fastmcp` + `/modelcontextprotocol/python-sdk` + `/hynek/structlog`; PyPI verified within 24h; MCP Spec 2025-06-18; FastMCP docs; Datasette JSON/FTS/settings; httpx Timeouts + Resource Limits; Claude Code issue #10606; Litestar GHSA-hm36-ffrh-c77c.

Secondary (MEDIUM): `anthropics/claude-for-legal`; `knowledge-work-plugins/legal`; OpenAI deep-research MCP contract; Anthropic Connectors Directory FAQ + submission guide; CourtListener MCP; Microsoft / Invariant Labs / Elastic on indirect prompt injection; Mark Amery / adam-p on XFF; haroldadmin / SQLite forum on FTS5 escaping; FastMCP issues #510 / #556.

---
*Research synthesis: 2026-05-13*
*Source documents: STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*
*Ready for roadmap: yes*

### Suggested phases: 9 (PRD milestone structure preserved)

1. **M1 — Skeleton + `list_databases`**
2. **M2 — Discovery + denylists**
3. **M3 — Structured retrieval**
4. **M4 — Search**
5. **M5 — Fragments**
6. **M6 — Envelope hardening + injection labels**
7. **M7 — Rate limit + errors + `/healthz` + logs**
8. **M8 — Tests + 24h soak**
9. **M9 — Submission PR**
