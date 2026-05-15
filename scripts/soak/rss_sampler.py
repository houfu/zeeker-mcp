"""RSS memory sampler for the 24h soak harness — TEST-05 / NFR-03.

Pure-stdlib module (plus httpx for the remote-metrics path; httpx is already
in the locked dep set so no NFR-04 violation).

Three modes:
  - rss_kb_from_proc(pid)   — local /proc/{pid}/status read (Linux)
  - rss_kb_from_self()      — local resource.getrusage fallback (macOS / non-Linux)
  - rss_kb_from_remote(...) — GET <base_url>/admin/metrics with X-Soak-Bypass token,
                              parse {"rss_kb": int} (soak against remote production)

macOS vs Linux unit difference:
  Linux:  resource.ru_maxrss is in KB (cumulative-max since process start).
  macOS:  resource.ru_maxrss is in BYTES (current RSS).
This is the entire reason this helper exists — to normalise the two units.

Note: psutil is explicitly REJECTED per NFR-04 (tests/test_dependency_footprint.py).
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def rss_kb_from_proc(pid: int) -> int | None:
    """Return resident-set in KB by reading /proc/{pid}/status — Linux only.

    Reads the VmRSS field from the kernel pseudo-file. Returns None on:
      - non-Linux platforms (OSError: /proc not present)
      - unreadable PID (process gone, permissions)
      - missing VmRSS field (unexpected kernel/container config)
    """
    try:
        text = Path(f"/proc/{pid}/status").read_text()
        m = re.search(r"^VmRSS:\s+(\d+)\s*kB", text, re.MULTILINE)
        return int(m.group(1)) if m else None
    except (OSError, AttributeError):
        return None


def rss_kb_from_self() -> int:
    """Fallback for non-Linux: ru_maxrss from current process, normalised to KB.

    macOS reports bytes; Linux reports KB.
    The conditional branch on os.uname().sysname == "Darwin" is unusual in this
    codebase (no other module checks platform) — it is intentional here because
    normalising to KB is the only reason this helper exists.
    """
    import resource  # local import so the module loads cleanly on platforms without resource

    rusage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS reports bytes; Linux reports KB. Normalize to KB.
    if os.uname().sysname == "Darwin":
        return rusage.ru_maxrss // 1024
    return rusage.ru_maxrss


async def rss_kb_from_remote(client, base_url: str, token: str) -> int | None:
    """Read RSS from the server's /admin/metrics endpoint.

    Used when the soak driver runs against a remote production endpoint
    (mcp.zeeker.sg) and `/proc/{pid}/status` is unreachable.

    Args:
      client: an httpx.AsyncClient (caller owns its lifecycle)
      base_url: base URL of the running mcp server (e.g. "https://mcp.zeeker.sg")
      token: the SOAK_BYPASS_TOKEN value to send in X-Soak-Bypass

    Returns:
      The rss_kb integer from the JSON body, or None if:
        - the request fails (network error, timeout)
        - the response is non-200 (404 = token mismatch on the server)
        - the body is malformed
    """
    if not token:
        return None
    try:
        resp = await client.get(
            f"{base_url.rstrip('/')}/admin/metrics",
            headers={"X-Soak-Bypass": token},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None
        body = resp.json()
        rss = body.get("rss_kb")
        return int(rss) if isinstance(rss, int) else None
    except Exception:  # noqa: BLE001 — sampler must never crash the soak loop
        return None
