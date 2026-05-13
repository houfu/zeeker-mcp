# src/mcp_zeeker/core/ip.py
# Source: 01-RESEARCH.md Pattern G lines 561–600 (paste verbatim, import-path adjusted)
from __future__ import annotations

from starlette.requests import HTTPConnection

from mcp_zeeker import config


def client_ip(conn: HTTPConnection) -> str:
    """
    Return the best-guess client IP, given exactly TRUSTED_PROXY_DEPTH
    trusted reverse proxies between us and the public internet.

    Phase 1: TRUSTED_PROXY_DEPTH defaults to 1 (Caddy). Phase 7 may make
    this configurable per RATE-03. We read XFF right-to-left and drop the
    trailing N trusted hops; the remaining rightmost entry is the client.
    """
    depth = getattr(config, "TRUSTED_PROXY_DEPTH", 1)
    xff = conn.headers.get("x-forwarded-for", "")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        # parts = [client, proxy1, proxy2, ...]; rightmost depth entries are trusted
        # but with depth=1 and one trusted hop that has *overwritten* XFF,
        # parts == [client_ip] and we return parts[0].
        if len(parts) <= depth:
            return parts[0] if parts else ""
        return parts[-(depth + 1)]
    # No XFF header — fall back to the immediate peer (loopback in our topology)
    return conn.client.host if conn.client else ""


def ip_prefix(ip: str) -> str:
    """OBS-04: log only the /24 prefix to avoid full-IP retention."""
    if not ip:
        return ""
    if ":" in ip:  # IPv6 — take first 3 groups
        return ":".join(ip.split(":")[:3])
    parts = ip.split(".")
    return ".".join(parts[:3]) if len(parts) == 4 else ip
