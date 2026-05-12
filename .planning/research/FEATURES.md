# Feature Research

**Domain:** Remote MCP server for primary-source Singapore legal data (judgments, PDPC enforcement decisions, government newsroom releases, legal commentaries) consumed by Claude through the `anthropics/claude-for-legal` plugin suite.
**Researched:** 2026-05-13
**Confidence:** HIGH for the OpenAI/Anthropic MCP tool contracts (verified against current docs); MEDIUM for the `claude-for-legal` plugin-side citation guardrails (inferred from the public `knowledge-work-plugins/legal` repo, which is the canonical CONNECTORS.md for these plugins); LOW for any specific "regulatory primary source" wishlist (Anthropic's published CONNECTORS.md uses tool-agnostic `~~category` placeholders rather than a primary-sources wishlist — the PRD's framing reflects ecosystem signals, not a codified registry slot).

> Important clarification surfaced during research: the public `anthropics/claude-for-legal` / `knowledge-work-plugins/legal/CONNECTORS.md` is a **placeholder taxonomy** (calendar, chat, cloud storage, CLM, CRM, email, e-signature, office suite, project tracker) — not a queue of wanted primary-source connectors. Submitting a Singapore primary-source connector means adding it to a specific plugin's `.mcp.json` *and* convincing maintainers that the plugin's skills will exercise it. The de-facto contract Zeeker is being held to is the **citation-verification contract**: each citation a plugin emits must either be tagged with a connector source or be marked `[verify]`. Zeeker's connector earns trust by producing citation-ready, source-tagged output. That is the real submission contract.

## Feature Landscape

### Table Stakes (Required for Registry Acceptance and LLM Usability)

Without these, the connector will either be rejected from the `claude-for-legal` PR review or be functionally unusable to an LLM agent in the agent loop.

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| **`search` + `fetch` pair** with predictable shapes | This is the cross-platform de-facto MCP contract: OpenAI's deep-research connectors *require* exactly this pair with `search → {results: [{id, url, ...}]}` and `fetch(id) → document`. Anthropic's reference Fetch server is built on the same primitive ("Search finds the URLs; Fetch reads them"). An LLM that has been trained on these patterns will reach for them first. | LOW | PRD has both. Validate envelope shape matches the OpenAI deep-research compatibility schema so the connector also works outside Claude. |
| **Provenance/citation envelope on every response** | The `claude-for-legal` citation guardrail flags citations that aren't tagged with a connector source as `[verify]`. A connector that doesn't emit source/url/date/license per result will cause Claude to refuse to cite from it. | LOW | PRD §8 covers this. The `citation` synthesis fallback (URL + date when no native citation field) is critical for PDPC. |
| **URL/ID as the universal addressing scheme** | OpenAI deep-research spec: `search` results must include an `id` that `fetch` can resolve. Anthropic's pattern uses URLs the same way. Internal PKs are forbidden — they leak platform internals and break across deployments. | LOW | PRD's "URL is the universal addressing scheme" decision aligns perfectly. |
| **Read-only annotation (`readOnlyHint: true`) on every tool** | The 2025-03-26 MCP spec introduced tool annotations. Clients (especially Claude) use `readOnlyHint` to decide whether to auto-approve calls inside an agent loop. Without it, every tool call needs human approval — kills the UX. | LOW | Trivially added in FastMCP via the `annotations` parameter. PRD doesn't mention this; **gap**. |
| **Predictable, enumerated error codes** | LLMs recover better from structured errors. Documented best practice: every error must tell the LLM *what went wrong* and *how to recover*. Codes like `rate_limited` with `retry_after_seconds`, `unknown_column` with the list of valid columns, are the standard. | MEDIUM | PRD §12 covers the codes. Enhancement: each error should include a recovery hint (e.g., `unknown_column` should return the valid column list). |
| **Hidden-data stripping (denylist enforced in both directions)** | Two-sided contract: (a) reject requests that *reference* hidden tables/columns/PKs; (b) strip hidden fields from *responses* (including search-result rows). Either side missing leaks platform internals. | MEDIUM | PRD §9.1/9.2 covers this. Verify the strip happens after fragment-join so internal FKs never appear. |
| **Tool descriptions that fit the agent's context budget** | Industry guidance: tool descriptions consume tokens on every request; 50 tools eats 5-7% of context. Anthropic's own guidance: most important info first sentence, 1-2 sentences total, plus parameter-level docs. | LOW | PRD's six-tool surface is well-sized. The trailing safety sentence is +24 tokens × 6 tools = ~150 tokens overhead, acceptable. |
| **Injection-resistance posture (labeling, not filtering)** | Anthropic and the MCP security best-practices doc both call out indirect prompt injection from retrieved third-party content as a primary threat. For *legal* corpora, lexical filtering is wrong (judgments legitimately discuss adversarial prompts, jailbreaks, instructions); consistent envelope labeling + tool-description discipline is the documented mitigation. | LOW | PRD §10 nails this. The fixed trailing sentence is the right move. |
| **Pagination via opaque cursor** | MCP spec recommends cursor-based pagination over offset-based because legal data is append-only (new judgments arrive); offsets can duplicate or skip rows between calls. Datasette's `_next` token is already opaque, so pass-through is correct. | LOW | PRD §7.5 covers. Verify the cursor is base64-or-similar so the LLM doesn't try to decode/edit it. |
| **Discovery surface (`list_databases`, `list_tables`, `describe_table`)** | Without these, the agent can't introspect on a cold session and must hard-code names. The `describe_table` distinction between "light columns" (default) and "available columns" (opt-in) is what lets the LLM make informed `columns` requests without trial-and-error. | LOW | PRD §7.1-7.3 covers. The light-vs-full distinction in `describe_table` is the cleverest feature here and should be highlighted in tool descriptions. |
| **`/healthz` + structured logs** | Operator requirement; the `claude-for-legal` review will check that the server is operable in production. JSON logs with request ID + tool + db + table + duration + IP-prefix is the documented standard. | LOW | PRD §13 covers. Add the request ID to the error envelope too (operators need it for incident response). |
| **Rate limit semantics surfaced in tool descriptions** | If the LLM doesn't know that a 429 with `Retry-After` is recoverable, it will treat it as a permanent failure and abandon the task. Documenting the limits in the tool description (one line) lets the LLM plan around them. | LOW | PRD §11 mentions this; make sure it's in the actual `description=` string the LLM sees, not just the docs. |
| **Schema-validated input on every tool** | FastMCP gives this for free via Pydantic. Required for safe SQL parameter binding and for letting the LLM understand parameter shapes via the tools/list response. | LOW | PRD constraint covers (`pydantic` is in the stack). Use Pydantic models for filter triples to constrain `op` to the enumerated set. |
| **Bounded default response sizes** | A single `fetch` returning a 500 KB judgment text blows the agent's context budget. Default to metadata + short summary; require explicit opt-in for heavy text. | MEDIUM | PRD §7.6 and §9.4 implement this via the light-column model and `retrieved_content` wrapping. This is one of Zeeker's strongest design points. |
| **TLS + public reachability from Anthropic IP ranges** | Connector registry requirement: server must be reachable over the public internet from Anthropic's IPs; servers behind VPNs/firewalls won't connect. | LOW | Operator concern per PRD §6; document the IP allowlist requirement in deployment notes. |
| **Streamable HTTP transport (with SSE fallback)** | Current MCP transport spec; non-negotiable for remote connectors. | LOW | PRD covers via FastMCP. |

### Differentiators (Materially Improve Agent UX vs Generic Datasette Wrapper)

These are where Zeeker can stand out from a hypothetical "raw Datasette → MCP" wrapper. Each one is an opportunity that ecosystem peers haven't standardized on.

| Feature | Value Proposition | Complexity | Notes |
|---|---|---|---|
| **Transparent fragment-parent join via URL filter** | The agent never sees internal PKs/FKs; it filters fragments by the parent's URL (the same URL it already has from `search` or `fetch`). One mental model — URL is the key — applies to every table. This is genuinely novel; no other public MCP connector I found does this transparently. | HIGH | PRD §7.5 / §9.5 cover. Server-side two-step: URL → parent PK → fragment query ordered by per-table order column. Test surface: parent missing, parent has zero fragments, ordering ties. |
| **Light vs heavy column separation with `retrieved_content` wrapper** | Default response is always small (a few KB); heavy text columns require explicit `columns=[...]` opt-in and are returned under a separate `retrieved_content` key. Bounds default token cost *and* visually labels the heavy text as data (not instructions) to the reading LLM. Two design goals served by one mechanism. | MEDIUM | PRD covers in §7.5 / §8 / §9.4. This deserves a callout in every tool description (the LLM needs to know that requesting `content_text` costs more tokens). |
| **Citation synthesis when no native citation field exists** | For tables without a `citation` column (PDPC enforcement), the server synthesizes a citation string from URL + date at envelope-build time. The agent always has *something* citable, regardless of source-table heterogeneity. | LOW | PRD §8 covers. Useful pattern: also synthesize a short-form citation suitable for inline use, not just the long form. |
| **Single-process, stateless, no-mirror design** | No divergence from upstream; every call is a clean request/response. Simplifies registry review (small audit surface, no DB driver, no cache invalidation logic). Aligns with `claude-for-legal`'s "Citations verified against current databases" requirement — a stale cache would violate that. | LOW | PRD §6 + constraints cover. Surface this in the README submission. |
| **Cross-database `search` with hidden-table post-filter** | Search hits in hidden tables (`metadata`, `schema_versions`) are stripped from results, so the agent can't accidentally discover them. The default of searching across all four databases (per PRD open question) is the right ergonomic choice — single tool call discovers across the whole corpus. | MEDIUM | PRD §7.4 covers. Confirm default is "all four" (PRD open question #3); recommend YES based on ecosystem norm of one query → broad results. |
| **Per-table URL-column mapping (config-driven)** | Every URL-keyed table maps its own URL column (`source_url`, `decision_url`, `source_link`, `link`, `item_url`). The mapping is hidden from the LLM, so it doesn't need to learn that PDPC uses `decision_url` while judgments use `source_url`. | LOW | PRD §9.3 covers. Worth documenting in `describe_table` output that "this table is URL-keyed for fetch()" without exposing which column. |
| **License/attribution baked into the envelope** | `CC-BY-4.0` + `data.zeeker.sg` attribution on every successful response means downstream consumers (the agent and any user-facing UI) always have what they need for proper attribution. Some legal connectors only expose license in metadata; surfacing it per-response is friendlier. | LOW | PRD §8 covers. If license varies per-table in future, structure makes this trivially extensible. |
| **Filter operator set tuned for legal use (date ranges, organisation lookups, contains)** | Default ops: `exact, not, contains, startswith, endswith, gt, gte, lt, lte, in, notin, isnull, notnull`. Covers all the question shapes from PRD §5 ("PDPC fined banks in last 18 months" = `gte` on date + `contains` on organisation). | MEDIUM | PRD §7.5 covers. Important: `contains` semantics must be SQL-LIKE (case behaviour documented) so the LLM doesn't get surprised by unicode/case mismatches. |
| **Structured "available columns" surface in `describe_table`** | Distinguishing the default (light) set from the full available set lets the LLM make a single informed opt-in for heavy content. Without this, the LLM has to either guess column names or call `query_table` with no `columns` and then realize the heavy text wasn't returned. | LOW | PRD §7.3 covers via the schema distinction. Make sure the response shape is something like `{"light_columns": [...], "available_columns": [...], "url_keyed": true, "supports_fragments": true}`. |
| **Rate-limit hints in tool descriptions + Retry-After in 429s** | Telling the LLM "20-burst / 60/min / 5k/24h" in the tool description, and including `retry_after_seconds` in the `rate_limited` error envelope, lets the agent loop plan correctly. Most MCP connectors don't surface this. | LOW | PRD §11 / §12 cover the mechanics; lift the limits into the visible tool descriptions. |
| **Tool annotations: `readOnlyHint`, `openWorldHint`, `idempotentHint`** | The 2025-03 MCP spec annotation set lets clients (Claude) auto-approve calls and parallelize them safely. For Zeeker, all six tools are `readOnly=true, idempotent=true, openWorld=true` (the upstream Datasette content changes). | LOW | **Not in PRD; add this.** FastMCP supports annotations as a parameter to `@mcp.tool()`. |
| **Request-ID echoed in error envelopes** | Operators investigating user-reported errors need to grep logs for the failing request; surfacing the request ID in the error payload halves incident-response time. | LOW | Not in PRD; cheap to add to the error envelope. |
| **Structured `health` payload from `/healthz` (upstream check)** | A `/healthz` that pings `data.zeeker.sg`'s `/-/versions.json` is more useful than one that just returns 200. Surface upstream status so the operator and the registry review can see end-to-end. | LOW | PRD §13 mentions `/healthz`; extend to include upstream check. |

### Anti-Features (Deliberately NOT Built)

These appear desirable on first read but are wrong for a primary-source legal-data connector. Each entry: why it's tempting + why it's wrong + the better approach.

| Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|
| **Raw SQL / `execute_sql` endpoint** | "Just give the LLM SQL and let it figure things out" — used by some Datasette-MCP wrappers and seems flexible. | (a) Massive attack surface from an LLM — SQL injection of every kind, including subtle ones the LLM doesn't know it's writing; (b) the LLM is bad at SQL on schemas it hasn't memorized — it generates broken queries and burns retries; (c) registry review surface explodes (you must prove no DoS, no information leakage, no path to hidden tables via subqueries); (d) Datasette's own `?sql=` interface is read-only-by-default but still leaks PRAGMA / `sqlite_master` / FK column names to anyone who queries it. | Opinionated `query_table` with enumerated operators. The LLM gets a predictable surface; the server retains control of what's queryable. PRD's choice. |
| **Write tools (insert/update/delete/post-comment-on-judgment)** | "Make the connector useful for editing data, not just reading" — looks like richer value. | (a) Zeeker upstream is read-only authoritative content — there's nothing to write to; (b) write tools 10x the registry review surface; (c) write tools require auth, which kills the anonymous-tier UX; (d) blast radius from a hallucinated write is catastrophic in a legal context. | Read-only by design. If write is ever needed (e.g., "save annotation"), it belongs in a separate per-user note-taking connector, not in the primary-source one. PRD's choice. |
| **Content scrubbing / lexical filtering of legal text** | "Protect against prompt injection by removing adversarial-looking content before returning it" — naive but common. | Legal documents legitimately quote adversarial content (jailbreak case law, fraud transcripts, threatening communications). Scrubbing degrades the corpus to uselessness. The MCP/Anthropic guidance is explicit: *labeling* (envelope discipline + tool description) beats *filtering* for adversarial-but-legitimate corpora. | Consistent `retrieved_content` wrapping + fixed trailing tool-description sentence. PRD §10 is correct. |
| **Auth-required-for-anonymous-use in v1** | "Always require API keys — easier to track abuse, easier to enforce per-user limits" — defensive but premature. | (a) Kills trivial adoption (`claude-for-legal` plugin authors won't include a connector that requires every user to manage a key for a public dataset); (b) Zeeker upstream is public/CC-BY anyway — no entitlement to protect; (c) the rate-limiter handles abuse; (d) the architecture already supports a key-swap upgrade path. | Anonymous tier in v1, IP-keyed rate limiter, function-pointer upgrade path to API keys documented in `RateLimiter` interface. PRD §11 covers. |
| **Persistent caching that diverges from upstream** | "Cache to reduce latency and upstream load" — sounds like good citizenship. | (a) Citations would silently go stale — a court opinion withdrawn upstream still returned by Zeeker = liability; (b) `claude-for-legal` *explicitly* requires "verified against current databases" — a cached layer violates that; (c) cache invalidation is a hard problem you'd be solving for marginal latency gain. | Stateless pass-through; each tool call hits upstream. If latency becomes a problem, add a *transparent* HTTP-cache layer with very short TTL (≤60s) and a `cache_age_seconds` field in the provenance envelope so the agent knows. PRD §6 + Out-of-Scope §16 cover. |
| **Aggregation tools at v1 (`count_by`, `group_by`, `histogram_over_dates`)** | "Let the agent ask analytical questions directly" — feels like obvious LLM use case. | (a) Datasette already returns aggregates via existing structured columns or facets — the agent can synthesize from query results; (b) aggregation amplifies the cost of any hidden-column or hidden-table leak (one query reveals counts across thousands of rows); (c) defining the right aggregation surface requires watching real usage — premature design. | Defer. If usage shows agents repeatedly counting and grouping, add `aggregate_table(database, table, group_by, agg)` in v1.x with a tight allow-list. PRD §16 covers. |
| **Subscription / push for new judgments or enforcement decisions** | "Let the agent subscribe to new content as it lands" — sounds like LLM-friendly. | (a) MCP protocol doesn't have great push semantics today (notification model is for client-server, not agent-to-server); (b) requires per-user state — kills the stateless design; (c) the typical agent loop is one-shot, not long-lived — push has no consumer. | Defer. The agent can poll `query_table` with a date filter on each session. PRD §16 covers. |
| **`/status` mirror of Zeeker's status endpoint** | "Operators want a status page; mirror upstream's." | Pure indirection — the operator can hit `data.zeeker.sg`'s status directly. The MCP layer adds no value here, only confusion. | `/healthz` proves the MCP server itself is up; upstream status is upstream's problem. PRD covers. |
| **A "describe everything" mega-tool** | "Combine `list_databases + list_tables + describe_table` into one `introspect()` call to save round-trips." | (a) Token cost — a single response would be 5-20 KB; (b) the LLM doesn't need most of it on most calls; (c) MCP tools/list already does this at session-start cost; (d) the discovery surface composes naturally over multiple calls. | Three small tools, each composable. PRD's choice. |
| **Hidden-table exposure under a "debug" flag** | "Let advanced users see internal tables for debugging." | Defeats the entire hidden-data contract. Once exposed, the LLM will *use* the hidden tables (FK joins via `id`) and the agent loop becomes brittle. | Hidden means hidden, full stop. PRD's choice. |
| **Returning multiple result shapes from one tool (e.g., `query_table` returning either rows or aggregates)** | "Polymorphism is flexible." | LLMs handle predictable shapes much better than polymorphic ones. Each shape variant is a chance for the LLM to mis-parse. | One tool, one shape. If aggregates are needed later, separate tool with separate shape. |
| **`fetch_text(url)` that returns the full content_text directly** | "Give the agent a one-shot way to get the full text of a judgment." | Defeats the light-vs-heavy column model. The agent would default to this call because it's a single round-trip, blowing context budget. | Force the agent to opt in explicitly: `query_table(database='zeeker-judgements', table='judgments', filters=[{col:'source_url', op:'exact', value:url}], columns=['content_text'])`. The verbosity is the feature. |
| **Verbose multi-paragraph tool descriptions** | "Help the LLM understand the tool by explaining everything." | Token cost on every request; LLMs only read the first sentence reliably. The MCP best-practice guidance is 1-2 sentences with the critical info first. | One-sentence purpose, one sentence with critical constraints (rate limit, opt-in columns), trailing safety sentence. PRD design language is correct. |

## Feature Dependencies

```
[Streamable HTTP transport] (M1 foundation)
    └──requires──> [FastMCP + Starlette/Uvicorn]
    └──enables──> [list_databases] (M1 first tool, proves transport)
                       └──requires──> [Datasette client (httpx.AsyncClient)]

[list_databases]
    └──enables──> [list_tables] (M2)
                       └──requires──> [Hidden-table denylist (config.py)]
                       └──enables──> [describe_table] (M2)
                                          └──requires──> [Hidden-column denylist]
                                          └──requires──> [Light-vs-available column sets]

[describe_table]
    └──enables──> [query_table] (M3 — the heart of the connector)
                       └──requires──> [Filter operator mapping → Datasette query string]
                       └──requires──> [Cursor pagination pass-through]
                       └──requires──> [columns parameter validation against schema]
                       └──requires──> [Hidden-column rejection on filters/sort/columns]
                       └──enables──> [fetch] (M3 — wraps query_table with URL-keyed lookup)
                                          └──requires──> [URL-column per-table mapping (config.py)]

[query_table on fragment tables] (M5 — depends on M3)
    └──requires──> [Fragment-parent map (config.py)]
    └──requires──> [Two-step server-side resolution: URL → parent PK → fragment FK query]
    └──requires──> [Internal PK/FK never leaves the server (hidden-column denylist)]

[search] (M4 — independent of fetch/query semantically, but shares envelope)
    └──requires──> [Hidden-table post-filter on search results]
    └──requires──> [Preview-row column selection (never heavy text)]

[Provenance envelope] (M6 — applied to all tool responses)
    └──requires──> [Citation synthesis fallback for tables without native citation]
    └──requires──> [retrieved_content wrapper for heavy text columns]
    └──enables──> [Citation-verification contract with claude-for-legal plugins]

[Tool-description discipline + readOnlyHint annotations] (M6)
    └──requires──> [Fixed trailing sentence on every tool description]
    └──requires──> [readOnlyHint, idempotentHint, openWorldHint annotations]
    └──enables──> [Agent auto-approval in agent loop]

[Rate limiter] (M7)
    └──requires──> [In-memory token bucket keyed by X-Forwarded-For IP]
    └──requires──> [rate_limited error code + retry_after_seconds]
    └──enables──> [Anonymous-tier viability]
    └──enables──> [Upgrade path to API-key-keyed limits (function-pointer swap)]

[Structured error catalog] (M7)
    └──requires──> [Stable error codes (PRD §12)]
    └──enables──> [LLM-friendly recovery hints in error responses]

[/healthz + structured JSON logs] (M7)
    └──enables──> [Operator observability + registry-review credibility]

[Tests covering envelope shape, hidden-data, fragment joins, rate limits] (M8)
    └──requires──> All M1-M7 features stable
    └──enables──> [Submission credibility (M9)]

[claude-for-legal PR submission] (M9)
    └──requires──> All above
    └──requires──> [Per-plugin .mcp.json entry + README]
    └──requires──> [Documented IP-allowlist requirements (Anthropic IP ranges)]
```

### Dependency Notes

- **Hidden-table/column denylist is upstream of every tool except `list_databases`** — it must be implemented before `list_tables` and stay correct through every later feature. A leak found in M8 testing means rework across M2-M5.
- **Fragment-parent join depends on `query_table` being stable** — fragment logic adds a server-side two-step on top of `query_table`'s normal flow. Build `query_table` first (M3), then layer fragments (M5).
- **Provenance envelope depends on every tool's response shape being settled** — wire the envelope last (M6) so you wrap a known shape, not a moving target. PRD milestone ordering correctly puts envelope at M6.
- **`readOnlyHint` annotations should be wired in M1 with the first tool**, not deferred — they cost nothing and clients (Claude) start benefiting immediately. PRD doesn't mention them; flag this as an M1 addition.
- **Citation synthesis fallback is gated on knowing which tables lack a native `citation` field** — survey the four databases during M2 (`describe_table`) and bake the mapping into `config.py` before M6.
- **Tool descriptions are written *throughout*** — every tool gets its description, rate-limit mention, and trailing safety sentence when it's registered. Don't defer description language to M6.

## MVP Definition

### Launch With (v1 — Aligned to PRD Milestones M1-M9)

These are the table-stakes features plus the differentiators that are central to Zeeker's value proposition (citation-ready, scope-bounded, safe-to-feed-back).

- [ ] **Six MCP tools** (`list_databases`, `list_tables`, `describe_table`, `search`, `query_table`, `fetch`) — the surface the LLM uses
- [ ] **Provenance envelope on every success response** — the citation contract with `claude-for-legal`
- [ ] **Hidden-table and hidden-column enforcement** (denylist + request rejection + response stripping) — zero-leakage commitment
- [ ] **Light vs heavy column model with `retrieved_content` wrapper** — bounded default tokens + injection labeling
- [ ] **URL-keyed `fetch`** for tables with per-table URL mappings — universal addressing scheme
- [ ] **Transparent fragment-parent join** via URL filter on `*_fragments` tables — agent never sees internal PKs/FKs
- [ ] **Cross-database `search`** with hidden-table post-filter and preview-only rows — single tool call discovery
- [ ] **Injection-resistance posture**: `retrieved_content` wrapping + fixed trailing sentence in every tool description — labeling-not-filtering
- [ ] **In-memory token-bucket rate limiter** (20-burst / 60-min / 5k-24h) keyed by IP, with `Retry-After` in 429s
- [ ] **Structured MCP error catalog** with stable codes from PRD §12, including `retry_after_seconds` in `rate_limited`
- [ ] **`readOnlyHint`, `idempotentHint`, `openWorldHint` annotations on every tool** — **PRD addition: not currently listed**
- [ ] **Rate-limit semantics in visible tool descriptions** so the LLM knows 429 is recoverable
- [ ] **Citation synthesis fallback** for tables without native citation fields (PDPC enforcement)
- [ ] **`/healthz` endpoint + structured JSON logs** with request ID, tool, db, table, duration, status, IP-prefix
- [ ] **Request ID echoed in error envelopes** — **PRD addition: enhances operator debuggability**
- [ ] **Test coverage** of all hidden-data paths, fragment joins, envelope shape, rate-limit windows, error mapping
- [ ] **Per-plugin `.mcp.json` PR** to `anthropics/claude-for-legal` (target: `regulatory-legal` first, `ai-governance-legal` second, `litigation-legal` third — per PRD open question)

### Add After Validation (v1.x — Triggered by Real Usage)

- [ ] **Aggregation tool** (`aggregate_table`) — add only if logs show agents repeatedly counting/grouping by hand
- [ ] **API-key auth tier** with per-key limits — add when anonymous abuse becomes measurable
- [ ] **Short-TTL transparent HTTP cache** (≤60s, with `cache_age_seconds` in provenance) — add only if p95 latency degrades
- [ ] **Faceted search results** (top-N organisations, top-N years) — add if agents ask "summarize PDPC enforcement by year" style queries
- [ ] **`describe_database`** with cross-table relationships — add if agents struggle to discover fragment-parent links

### Future Consideration (v2+)

- [ ] **Redis-backed distributed rate limiting** — only when single-process saturates (very unlikely for anonymous public read)
- [ ] **Subscription / push for new content** — only when MCP push semantics stabilize and agent loop supports long-lived sessions
- [ ] **Cross-corpus joins** (e.g., "judgments that cite a PDPC decision") — high value but requires a join-aware query layer
- [ ] **Multi-language support** (Singapore is multilingual) — only if upstream corpora gain non-English content
- [ ] **Plug-in additional Singapore primary sources** (statutes, gazette, regulator decisions) — extends value proposition

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---|---|---|---|
| Six tools with predictable shapes | HIGH | MEDIUM | P1 |
| Provenance envelope | HIGH | LOW | P1 |
| Hidden-data enforcement | HIGH | MEDIUM | P1 |
| Light/heavy column model | HIGH | MEDIUM | P1 |
| URL-keyed fetch | HIGH | LOW | P1 |
| Fragment-parent join | HIGH | HIGH | P1 |
| Cross-DB search | HIGH | MEDIUM | P1 |
| Injection-resistance labeling | HIGH | LOW | P1 |
| Rate limiter (IP-keyed) | HIGH | MEDIUM | P1 |
| Structured error catalog | HIGH | LOW | P1 |
| Tool annotations (`readOnlyHint` etc.) | MEDIUM | LOW | P1 |
| Rate-limit hints in tool descriptions | MEDIUM | LOW | P1 |
| Citation synthesis fallback | HIGH | LOW | P1 |
| `/healthz` + structured logs | MEDIUM | LOW | P1 |
| Request ID in error envelopes | MEDIUM | LOW | P1 |
| Test coverage (hidden-data, fragments, rate limits, errors) | HIGH | MEDIUM | P1 |
| `.mcp.json` PR to claude-for-legal | HIGH | LOW | P1 |
| Aggregation tool | LOW | MEDIUM | P3 |
| API-key auth | LOW | MEDIUM | P3 |
| Short-TTL cache | LOW | MEDIUM | P3 |
| Redis-backed limiter | LOW | HIGH | P3 |
| Subscription / push | LOW | HIGH | P3 |
| Cross-corpus joins | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for v1 submission
- P2: Should have, add when validated
- P3: Nice to have, future consideration

## PRD Six-Tool Design: Assessment vs Ecosystem Expectations

The PRD's choice of `list_databases`, `list_tables`, `describe_table`, `search`, `query_table`, `fetch` is **conservative on the high-risk dimensions and aggressive on the right ergonomic dimensions**. Specifically:

### Conservative (correctly so)

- **No `execute_sql`** — every Datasette-MCP wrapper I found in the wild that exposes raw SQL has a documented information-leakage path. Zeeker's opinionated surface is the safer choice and aligns with the `claude-for-legal` registry's review posture.
- **No write tools** — matches the read-only primary-source positioning and minimizes registry-review surface.
- **No aggregation primitives** — deferred until usage signal warrants. This is the right call; aggregation amplifies leakage cost.
- **No persistent caching** — keeps citations live, which is mandatory for the `claude-for-legal` citation guardrail.

### Aggressive (and correct)

- **`search` + `fetch` pair** matches both the OpenAI deep-research contract and the Anthropic reference Fetch-server pattern. Cross-platform compatibility is a feature.
- **Transparent fragment-parent join inside `query_table`** is *more* ambitious than any peer MCP connector — most expose fragment tables raw, requiring the agent to figure out joins. Zeeker hides the complexity behind the URL-as-key model.
- **Light vs heavy column separation with `retrieved_content`** is a stronger token-budget discipline than any peer connector I surveyed. CourtListener's MCP, for example, returns full opinion text by default.

### Missing (recommend adding to PRD)

- **Tool annotations** (`readOnlyHint`, `idempotentHint`, `openWorldHint`) — trivial to add, materially improves agent-loop UX, currently absent from PRD.
- **Request ID in error envelopes** — costs nothing, helps operators.
- **Upstream health check inside `/healthz`** — currently `/healthz` is presumed to just return 200; adding an upstream ping makes it operationally useful.
- **Explicit "available_columns" surface in `describe_table` response** — PRD §7.3 implies this distinction but doesn't specify the response shape. Recommend codifying.
- **Documented Anthropic IP allowlist requirement** — operator-facing, required for the deployment to work with Claude at all. Should be a README item.

### Not Missing (well-handled in PRD)

- Citation synthesis, hidden-data enforcement, fragment joins, light-column model, envelope shape, error catalog, rate limit semantics — all crisply specified.

### One Open Design Question Worth Resolving Before M3

The PRD's filter operator list (`exact, not, contains, startswith, endswith, gt, gte, lt, lte, in, notin, isnull, notnull`) is sensible. **Recommend documenting `contains` case-sensitivity behavior explicitly in the tool description**: SQLite's `LIKE` is case-insensitive for ASCII by default but case-sensitive for unicode. Legal corpora often have proper names with accents (Asian names in Singapore judgments); an LLM that doesn't know this will write filters that silently miss results.

## Sources

### Anthropic / claude-for-legal
- [GitHub: anthropics/claude-for-legal](https://github.com/anthropics/claude-for-legal)
- [GitHub: anthropics/knowledge-work-plugins — legal/CONNECTORS.md](https://github.com/anthropics/knowledge-work-plugins/blob/main/legal/CONNECTORS.md)
- [GitHub: anthropics/knowledge-work-plugins — legal/README.md](https://github.com/anthropics/knowledge-work-plugins/blob/main/legal/README.md)
- [Anthropic Connectors Directory FAQ](https://support.claude.com/en/articles/11596036-anthropic-connectors-directory-faq)
- [Building custom connectors via remote MCP servers (Claude Help)](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [Anthropic Goes All-In on Legal — LawSites coverage](https://www.lawnext.com/2026/05/anthropic-goes-all-in-on-legal-releasing-more-than-20-connectors-and-12-practice-area-plugins-for-claude.html)
- [Anthropic Unveils Claude for Legal — Legaltech Hub](https://www.legaltechnologyhub.com/contents/anthropic-unveils-claude-for-legal-with-12-new-plugins-20-mcp-connectors-and-more/)
- [Code execution with MCP (Anthropic engineering)](https://www.anthropic.com/engineering/code-execution-with-mcp)

### MCP specification and reference servers
- [Tools — Model Context Protocol spec (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [Security Best Practices — Model Context Protocol](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices)
- [Architecture overview — MCP](https://modelcontextprotocol.io/docs/learn/architecture)
- [Specification — MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [GitHub: modelcontextprotocol/servers (reference servers)](https://github.com/modelcontextprotocol/servers)
- [Fetch MCP Server by Anthropic — PulseMCP](https://www.pulsemcp.com/servers/modelcontextprotocol-fetch)

### OpenAI / deep-research contract
- [Building MCP servers for ChatGPT Apps and API integrations](https://developers.openai.com/api/docs/mcp)
- [MCP and Connectors — OpenAI API guide](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)
- [Deep research — OpenAI API guide](https://platform.openai.com/docs/guides/deep-research)
- [Building a Deep Research MCP Server — OpenAI Cookbook](https://cookbook.openai.com/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/readme)
- [OpenAI MCP Integration: ChatGPT's Requirements for MCP Servers — MCP Bundles](https://www.mcpbundles.com/blog/openai-mcp-search-fetch-standard)

### FastMCP
- [Tools — FastMCP](https://gofastmcp.com/servers/tools)
- [Type System and Result Conversion — DeepWiki for jlowin/fastmcp](https://deepwiki.com/jlowin/fastmcp/3.4-type-system-and-result-conversion)
- [MCP Tool Annotations Explained — ChatForest](https://chatforest.com/guides/mcp-tool-annotations-explained/)

### Datasette
- [JSON API — Datasette documentation](https://docs.datasette.io/en/stable/json_api.html)
- [Metadata — Datasette documentation](https://docs.datasette.io/en/latest/metadata.html)
- [Full-text search — Datasette documentation](https://docs.datasette.io/en/latest/full_text_search.html)

### Legal MCP analogues (CourtListener, etc.)
- [Model Context Protocol (MCP) Server for Agentic Access — CourtListener wiki](https://www.courtlistener.com/help/mcp/)
- [REST API v4.4 — CourtListener wiki](https://www.courtlistener.com/help/api/rest/)
- [GitHub: DefendTheDisabled/courtlistener-mcp](https://github.com/DefendTheDisabled/courtlistener-mcp)
- [Full CourtListener Data Access via API Now Included with Membership](https://free.law/2026/05/07/api-included-in-memberships/)

### MCP tool-design and UX best practices
- [MCP tool descriptions: overview, examples, and best practices — Merge](https://www.merge.dev/blog/mcp-tool-description)
- [MCP Tool Design: Why Your AI Agent Is Failing — DEV Community](https://dev.to/aws-heroes/mcp-tool-design-why-your-ai-agent-is-failing-and-how-to-fix-it-40fc)
- [Building LLM-Friendly MCP Tools — JetBrains RubyMine blog](https://blog.jetbrains.com/ruby/2026/02/rubymine-mcp-and-the-rails-toolset/)
- [MCP Server Rate Limiting: Implementation Guide for Production — Fastio](https://fast.io/resources/mcp-server-rate-limiting/)
- [Securing MCP Server Communications — Aembit](https://aembit.io/blog/securing-mcp-server-communications-best-practices/)
- [MCP server governance best practices — Tyk](https://tyk.io/learning-center/mcp-server-governance-best-practices/)

---
*Feature research for: remote MCP connector to Singapore legal primary sources via `data.zeeker.sg`, targeting the `claude-for-legal` plugin registry.*
*Researched: 2026-05-13*
