# Phase 2 Manual Client Verification — DISC-02/03/04/05

Walk this checklist against the DEPLOYED instance at `https://mcp.zeeker.sg/mcp`. Do NOT
use `localhost` — the point is to prove DNS + TLS + Caddy + the docker-network
sibling-container path all work end-to-end with the Phase 2 tools.

> **F-4 OBLIGATION — DRY-RUN OBLIGATORY before declaring plan complete.**
> Per 01-LEARNINGS.md F-4: every curl example in this document MUST be dry-run against
> the live deployed instance before marking Phase 2 complete. See the F-4 sign-off block
> at the bottom.

## Pre-conditions

All Phase 1 pre-conditions remain valid. Additionally:

- [ ] `mcp.zeeker.sg` resolves to the operator's host
- [ ] `https://mcp.zeeker.sg/healthz` returns HTTP 200 with body `{"status":"ok"}`:
  ```
  curl -sf https://mcp.zeeker.sg/healthz
  ```
- [ ] Trailing-slash redirect preserves HTTPS (F-1 regression check — commit 349a739):
  ```
  curl -sI -X POST https://mcp.zeeker.sg/mcp | grep -i ^location
  ```
  Must return `location: https://mcp.zeeker.sg/mcp/` — NOT `http://`.

- [ ] `initialize` handshake completes and returns Mcp-Session-Id (stateful path, if any) OR
  completes cleanly without one (stateless path, per commit 4ce06d5). With `stateless_http=True`,
  the response header `mcp-session-id` should be ABSENT:
  ```
  curl -sN -X POST \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual-curl","version":"0.1"}}}' \
    https://mcp.zeeker.sg/mcp/ -D -
  ```
  Expected: HTTP 200, no `mcp-session-id:` response header (F-3 invariant).

- [ ] `tools/list` returns exactly 3 tool names: `list_databases`, `list_tables`, `describe_table`.
  Run `initialize` first (required by MCP spec), then run `tools/list` in the same curl session.
  Because `stateless_http=True`, you do NOT need to capture an Mcp-Session-Id — each request
  is independent:
  ```
  curl -sN -X POST \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
    https://mcp.zeeker.sg/mcp/
  ```
  Expected: response body (in `data:` SSE event or JSON body) includes all three tool names:
  `list_databases`, `list_tables`, `describe_table`.

## Claude Desktop

1. Open `claude_desktop_config.json` (Settings → Developer → Edit Config)
2. Ensure `mcpServers` contains the zeeker entry:
   ```json
   {
     "zeeker": {
       "url": "https://mcp.zeeker.sg/mcp"
     }
   }
   ```
3. Restart Claude Desktop. Confirm zeeker appears as a connected MCP server.

### list_tables

- [ ] Open a new chat, type:
  > "What tables are available in the zeeker-judgements database?"
- [ ] Claude should call `list_tables(database="zeeker-judgements")` and present visible tables.
- [ ] Expected result: the response includes `judgments` and `judgments_fragments` table names.
  It must NOT include any table name beginning with `_zeeker` (hidden platform tables per DISC-03).
- [ ] Screenshot the full window. Save to `evidence/02-discovery/claude-desktop-list-tables.png`.

### describe_table

- [ ] In the same or a new chat, type:
  > "Describe the schema of the judgments table in zeeker-judgements."
- [ ] Claude should call `describe_table(database="zeeker-judgements", table="judgments")`.
- [ ] Expected result: response includes `light_columns`, `available_columns`, `url_keyed: true`,
  and `supports_fragments: true` for the judgments table.
- [ ] Screenshot the full window. Save to `evidence/02-discovery/claude-desktop-describe-table.png`.

## Claude Code

1. From the project root in a terminal:
   ```
   claude mcp add zeeker https://mcp.zeeker.sg/mcp
   ```
2. Confirm registration:
   ```
   claude mcp list
   ```
   Must show `zeeker` with status `connected`.

### list_tables via Claude Code

- [ ] Open Claude Code, type:
  > "Call list_tables for zeeker-judgements and show me the result."
- [ ] Claude should call `list_tables(database="zeeker-judgements")` and present the tables.
- [ ] Verify no `_zeeker`-prefixed tables appear in the output.
- [ ] Screenshot the response. Save to `evidence/02-discovery/claude-code-list-tables.png`.

### describe_table via Claude Code

- [ ] In Claude Code, type:
  > "Call describe_table for the judgments table in zeeker-judgements."
- [ ] Claude should call `describe_table(database="zeeker-judgements", table="judgments")`.
- [ ] Verify `light_columns`, `available_columns`, `url_keyed`, `supports_fragments` are present.
- [ ] Screenshot the response. Save to `evidence/02-discovery/claude-code-describe-table.png`.

## DISC-05 Side-Channel Acceptance (manual reinforcement)

The automated tests in Plan 02 cover the code-path identity of hidden-vs-nonexistent table
error messages. This section provides the UX-layer check: confirm the error messages the
operator (or Claude) sees are indistinguishable between the two cases.

- [ ] In Claude Desktop or Claude Code, invoke:
  > "Describe the schema of the metadata table in sglawwatch."
  (This is a hidden platform table — exists in upstream Datasette but must be denied.)
  Expected: error message containing `unknown_table: Table not found: sglawwatch.metadata`

- [ ] Immediately after, invoke:
  > "Describe the schema of the totally_fictitious_table table in sglawwatch."
  (This table does not exist at all.)
  Expected: error message containing `unknown_table: Table not found: sglawwatch.totally_fictitious_table`

- [ ] Visual confirmation: BOTH error message strings have the identical prefix
  `unknown_table: Table not found:` and identical structure — only the table identifier differs.
  This ensures clients cannot distinguish hidden from nonexistent tables via the error message.

## Acceptance

- Four tools are reachable from Claude clients: `list_databases`, `list_tables`, `describe_table`
  (three listed; `list_databases` covered in Phase 1).
- `list_tables(zeeker-judgements)` shows only non-platform tables (no `_zeeker` prefix).
- `describe_table(zeeker-judgements, judgments)` shows all expected metadata fields.
- DISC-05: hidden table error message is structurally identical to nonexistent table error.
- Four screenshots committed under `evidence/02-discovery/` (or deferral logged below).

## Troubleshooting

- **`list_tables` returns 0 tables or errors**: Check upstream Datasette is reachable.
  Run `curl -sf https://data.zeeker.sg/zeeker-judgements.json | python3 -m json.tool | head -20`
  to confirm table list.
- **Hidden tables appear in `list_tables` output**: DISC-03 denylist in
  `config.HIDDEN_TABLE_PREFIXES` is missing or not applied. Check `src/mcp_zeeker/tools/discovery.py`.
- **`describe_table` on hidden table returns data instead of error**: DISC-05 enforcement is
  broken. The tool should call `_check_hidden` before fetching column metadata.
- **`initialize` returns `mcp-session-id` header**: `stateless_http=True` has been removed from
  `mcp.http_app()` in `src/mcp_zeeker/app.py`. Check commit 4ce06d5 is still in the deployed image.
- **`tools/list` shows only 1 or 2 tools**: Phase 2 tools not registered — check
  `src/mcp_zeeker/server.py` for `list_tables` and `describe_table` tool definitions.

---

## F-4 Dry-Run Obligation

Per 01-LEARNINGS.md F-4: every curl example and CLI command in this checklist MUST be
dry-run against the live `https://mcp.zeeker.sg/mcp` instance BEFORE marking this plan
complete. Specifically:

- [ ] Every curl example in "Pre-conditions" has been executed against the live host
- [ ] The `tools/list` pre-check curl confirmed exactly 3 tool names
- [ ] Every CLI command in "Claude Code" has been executed end-to-end
- [ ] Every "expected response" assertion was hand-verified against the actual response
- [ ] The DISC-05 side-channel check was visually confirmed (error message identity)
- [ ] Any deviation was either (a) fixed in the checklist text, or (b) logged as a follow-up

**Screenshots:**
- [ ] `evidence/02-discovery/claude-desktop-list-tables.png` captured
- [ ] `evidence/02-discovery/claude-desktop-describe-table.png` captured
- [ ] `evidence/02-discovery/claude-code-list-tables.png` captured
- [ ] `evidence/02-discovery/claude-code-describe-table.png` captured

**Operator sign-off:** _Pending human action — dry-run NOT yet performed as of 2026-05-13._

> This task is a `checkpoint:human-action`. The automated agent has written this checklist
> and committed it; the actual walk-through against the live deployment requires a human
> at a keyboard with access to Claude Desktop and Claude Code. The SUMMARY.md records this
> as pending-human-action. To resume, walk every item above and fill in the sign-off line:
>
> `Operator sign-off: <name, date>`
