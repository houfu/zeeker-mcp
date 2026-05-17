---
phase: quick-260517-dvf
plan: 01
subsystem: tools
tags: [coercion, pydantic, before-validator, json-stringify, regression]
requirements:
  - QUICK-260517-dvf
dependency_graph:
  requires:
    - src/mcp_zeeker/tools/search.py::search
    - src/mcp_zeeker/tools/retrieval.py::query_table
    - src/mcp_zeeker/core/filter_compiler.py::Filter
  provides:
    - src/mcp_zeeker/tools/_param_coercion.py::_coerce_json_list
  affects:
    - tests/tools/test_param_coercion.py
key_files:
  created:
    - src/mcp_zeeker/tools/_param_coercion.py
    - tests/tools/test_param_coercion.py
  modified:
    - src/mcp_zeeker/tools/search.py
    - src/mcp_zeeker/tools/retrieval.py
decisions:
  - "Pre-coercion runs as a pydantic BeforeValidator (single audit point: src/mcp_zeeker/tools/_param_coercion.py)."
  - "Helper is non-recursive, non-narrowing, non-logging — soft pre-step only; malformed JSON falls through to pydantic's canonical list_type error verbatim."
  - "Tests dispatch through mcp_client.call_tool(...) so the regression hits FastMCP's real pydantic validation pipeline — direct `await search(...)` bypasses pydantic entirely (the Annotated[..., Field] metadata is only consumed at FastMCP dispatch time)."
  - "Locked error catalog (D3-12) NOT modified — no new code, no schema change."
metrics:
  duration: "~25 min"
  completed: 2026-05-17
---

# Quick 260517-dvf: Accept JSON-encoded string forms for list params

## One-liner

Wire a `BeforeValidator(_coerce_json_list)` into `search.databases`, `query_table.filters`, and `query_table.columns` so JSON-stringified list args from MCP clients (observed in real Claude sessions) clear pydantic validation instead of erroring with `list_type`.

## Problem

Real Claude session on `mcp.zeeker.sg` (2026-05-17) dispatched:

- `search(databases='["zeeker-judgements"]', query='Law Society v X')` → `1 validation error for call[search] databases: Input should be a valid list [type=list_type, input_value='["zeeker-judgements"]' (str), input_type=str]`
- `query_table(database='zeeker-judgements', table='judgments', filters='[{"column":"case_name","op":"contains","value":"Law Society"}]', ...)` → same shape, on `filters`.

The agent read the framework rejection as a tool quirk and silently fell back to web search — the user lost access to curated Singapore-legal sources.

Root cause: certain MCP clients `JSON.stringify` complex tool args before dispatch; pydantic 2.13 does not auto-coerce `str` → `list` at validation time.

## Solution

`pydantic.BeforeValidator` is a coercion seam that runs BEFORE the declared type's own validation step. A shared helper attempts a single `json.loads(v)` on string input; success flows the decoded value through pydantic's normal list validation, failure leaves the original string in place so pydantic emits its canonical `list_type` error verbatim.

No catalog change, no schema change visible to clients (`BeforeValidator` is invisible to JSON Schema generation by design in pydantic 2.13), no new dependency (`json` is stdlib).

## Source diff

### `src/mcp_zeeker/tools/_param_coercion.py` (new file)

```python
"""
Pre-coerce JSON-encoded string forms of list-typed tool params (WR-260517-dvf).
...
"""

from __future__ import annotations

import json

# WR-260517-dvf: some MCP clients (observed in real Claude sessions)
# JSON.stringify list-typed args. Pydantic 2.13 then rejects them with
# `type=list_type, input_type=str`. Pre-coerce strings via json.loads
# so successful decodes flow through pydantic's normal list validation;
# malformed input falls through to pydantic's standard list_type error.
# No recursion (single decode attempt), no type narrowing, no logging.


def _coerce_json_list(v: object) -> object:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, json.JSONDecodeError):
            return v
    return v
```

### `src/mcp_zeeker/tools/search.py` (1 import added, 1 annotation patched)

- Line 45: `from pydantic import Field` → `from pydantic import BeforeValidator, Field`
- Line 62 (new): `from mcp_zeeker.tools._param_coercion import _coerce_json_list`
- Lines 100-110 (`search.databases`): inserted `BeforeValidator(_coerce_json_list),` between `list[str] | None,` and `Field(...)`. Description / default unchanged.

### `src/mcp_zeeker/tools/retrieval.py` (1 import added, 2 annotations patched)

- Line 53: `from pydantic import Field` → `from pydantic import BeforeValidator, Field`
- Line 79 (new): `from mcp_zeeker.tools._param_coercion import _coerce_json_list`
- Lines 112-124 (`query_table.filters`): inserted `BeforeValidator(_coerce_json_list),` between `list[Filter] | None,` and `Field(...)`. Description / default unchanged.
- Lines 153-159 (`query_table.columns`): inserted `BeforeValidator(_coerce_json_list),` between `list[str] | None,` and `Field(...)`. Description / default unchanged.

## Tests — 9 parametrized cases

`tests/tools/test_param_coercion.py`:

| # | Test                                                              | Shape                  | Assertion                                       |
| - | ----------------------------------------------------------------- | ---------------------- | ----------------------------------------------- |
| 1 | `test_direct_list_passthrough[search.databases:direct_list]`      | A — direct list        | error string lacks `list_type`                  |
| 2 | `test_direct_list_passthrough[query_table.filters:direct_list]`   | A — direct list        | error string lacks `list_type`                  |
| 3 | `test_direct_list_passthrough[query_table.columns:direct_list]`   | A — direct list        | error string lacks `list_type`                  |
| 4 | `test_json_string_coerced[search.databases:json_string]`          | B — JSON-encoded string | error string lacks `list_type`                  |
| 5 | `test_json_string_coerced[query_table.filters:json_string]`       | B — JSON-encoded string | error string lacks `list_type`                  |
| 6 | `test_json_string_coerced[query_table.columns:json_string]`       | B — JSON-encoded string | error string lacks `list_type`                  |
| 7 | `test_malformed_json_still_raises_list_type[search.databases:malformed_json]` | C — malformed JSON | raises ToolError; `list_type` present in message |
| 8 | `test_malformed_json_still_raises_list_type[query_table.filters:malformed_json]` | C — malformed JSON | raises ToolError; `list_type` present in message |
| 9 | `test_malformed_json_still_raises_list_type[query_table.columns:malformed_json]` | C — malformed JSON | raises ToolError; `list_type` present in message |

All 9 dispatch through `mcp_client.call_tool(...)` so the regression hits FastMCP's real pydantic validation pipeline. Direct `await search(...)` bypasses pydantic (the `Annotated[..., Field]` metadata is consumed only at FastMCP dispatch time) and was therefore the wrong dispatch surface for this regression.

### RED → GREEN evidence

- **RED (before patch):** 3 failed, 6 passed. Shape A (3) and Shape C (3) passed; Shape B (3) failed with `pydantic ValidationError` carrying `list_type` — exactly the production failure.
- **GREEN (after patch):** 9 passed.

## Verification results

```
uv run pytest tests/tools/test_param_coercion.py -v   → 9 passed in 2.25s
uv run pytest tests/tools/ -q                          → 118 passed, 1 skipped in 4.95s
uv run pytest -q                                       → 484 passed, 14 skipped, 5 warnings in 9.97s
uv run ruff format --check <4 touched files>          → 4 files already formatted
uv run ruff check <4 touched files>                   → All checks passed!
```

## Grep audit

```
$ grep -rn "BeforeValidator(_coerce_json_list)" src/mcp_zeeker/tools/
src/mcp_zeeker/tools/search.py:103:        BeforeValidator(_coerce_json_list),
src/mcp_zeeker/tools/retrieval.py:115:        BeforeValidator(_coerce_json_list),
src/mcp_zeeker/tools/retrieval.py:155:        BeforeValidator(_coerce_json_list),
```

Exactly 3 wiring sites, matching the threat-model and plan's `key_links` block.

## Schema parity audit

Generated FastMCP tool schema for `search` and `query_table` after the patch — `BeforeValidator` is invisible to pydantic JSON Schema generation, so MCP clients see the same `{anyOf: [{type: array, items: ...}, {type: null}]}` shape they saw before:

```python
search.databases   → {'anyOf': [{'items': {'type': 'string'}, 'type': 'array'}, {'type': 'null'}], ...}
query_table.filters → {'anyOf': [{'items': {'$ref': '#/$defs/Filter'}, 'type': 'array'}, {'type': 'null'}], ...}
query_table.columns → {'anyOf': [{'items': {'type': 'string'}, 'type': 'array'}, {'type': 'null'}], ...}
```

Client-visible MCP tool surface is byte-identical. The published tool description text for all three params was NOT touched.

## Catalog untouched

- `src/mcp_zeeker/core/errors.py` — no diff.
- `CATALOG` / D3-12 locked error codes — no new code.
- `src/mcp_zeeker/tools/discovery.py`, `discovery_models.py`, `retrieval_models.py`, `search_models.py` — no diff.

## Deviations from plan

None of substance. Plan-level adjustments worth noting:

- **Test database choice.** Plan suggested `pdpc-enforcement-decisions` and `zeeker-judgements` for the `databases=[...]` param; actual `config.ALLOWED_DATABASES` is `("zeeker-judgements", "pdpc", "sg-gov-newsrooms", "sglawwatch")`. Used `pdpc` for the search test cases (any valid ALLOWED_DATABASES member works since the regression is about pydantic validation, not the membership check downstream).
- **Test dispatch surface.** Plan's `<behavior>` section described direct `await search(...)` invocations; that path bypasses pydantic entirely in this codebase (handler is a plain async function — the `Annotated` metadata is only consumed at FastMCP dispatch time). Switched to `mcp_client.call_tool(...)` so the test hits the same pipeline that broke in production. Verified that this surface DOES emit the `list_type` error in the RED run — production-faithful.
- **httpx_mock options.** Added `pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False, assert_all_requests_were_expected=False)` plus a catch-all 503 in the `datasette_client` fixture so the handler bodies for Shape A and B reach a normal `upstream_unavailable` error rather than failing the suite on an "unexpected request" assertion from pytest-httpx. Standard idiom — matches existing test patterns in this repo (`test_search_errors.py` uses individual `add_response` per branch; here the catch-all keeps the param-coercion regression terse).
- **Helper hit count.** Plan's grep-audit checklist mentioned "exactly 4 hits of `_coerce_json_list`" across `src/mcp_zeeker/tools/`; actual count is 6 (1 def + 2 imports + 3 uses). The discrepancy is because the plan counted "import + use per file" as 1, but each is a separate grep hit. What matters: 3 wiring sites (verified), 1 sole definition (verified). No auto-fix needed.

## Production-incident verification

Spot-check via `Client(mcp).call_tool('search', {'query': 'x', 'databases': '["zeeker-judgements"]'})` — pydantic now accepts; subsequent error is `RuntimeError: DatasetteClient.current() called outside a bound scope` (ad-hoc invocation context only). The production path will continue past validation into the real handler body, where `unknown_database` / `upstream_unavailable` / a normal envelope all become reachable outcomes.

## Self-Check

- [x] `src/mcp_zeeker/tools/_param_coercion.py` exists with the WR-260517-dvf comment block and a single `_coerce_json_list` function (signature `(v: object) -> object`).
- [x] `src/mcp_zeeker/tools/search.py` imports `BeforeValidator` and `_coerce_json_list`; `search.databases` annotation carries `BeforeValidator(_coerce_json_list)`. No other behavioral change.
- [x] `src/mcp_zeeker/tools/retrieval.py` imports `BeforeValidator` and `_coerce_json_list`; both `query_table.filters` and `query_table.columns` annotations carry `BeforeValidator(_coerce_json_list)`. No other behavioral change.
- [x] `tests/tools/test_param_coercion.py` exists with 9 parametrized cases (3 params × {direct list, JSON string, malformed JSON}) — all 9 pass.
- [x] `uv run pytest -q` green (484 passed, 14 skipped — skips are pre-existing live-mode/surrogate-canary skips).
- [x] `uv run ruff format --check` and `uv run ruff check` clean on all 4 touched files.
- [x] Grep audit: `BeforeValidator(_coerce_json_list)` appears at exactly 3 wiring sites.
- [x] No diff in `core/errors.py`, `CATALOG`, `discovery.py`, `discovery_models.py`, `retrieval_models.py`, `search_models.py`, or any caller.
- [x] Schema audit: published JSON Schema for `databases` / `filters` / `columns` is byte-identical post-patch.

## Self-Check: PASSED
