"""24h soak driver for the mcp-zeeker connector — TEST-05.

Drives a running mcp-zeeker server with a synthetic workload and writes
per-request latency + per-minute RSS samples to CSV. Post-run report.py
converts the CSVs to a markdown summary artifact.

Two run modes:

  Local (against a local uvicorn for dev / smoke testing):
    Terminal A: uv run uvicorn mcp_zeeker.app:app --host 127.0.0.1 --port 8000 --workers 1
    Terminal B: uv run python -m scripts.soak.run_soak \\
                  --duration 86400 --concurrency 50 \\
                  --target-url http://127.0.0.1:8000 \\
                  --server-pid <pid>

  Remote (against production at mcp.zeeker.sg — the GHA workflow path):
    export SOAK_BYPASS_TOKEN=<secret>
    uv run python -m scripts.soak.run_soak \\
        --duration 86400 --concurrency 50 \\
        --target-url https://mcp.zeeker.sg

    When SOAK_BYPASS_TOKEN is set in the environment, the driver:
      - Sends X-Soak-Bypass: $SOAK_BYPASS_TOKEN on every tools/call request
        (server skips rate limit for these — see core/middleware/rate_limit.py)
      - Polls <target>/admin/metrics every --rss-sample-interval seconds for
        the server's resident memory (see core/admin.py)

NFR-01: p50 < 300ms, p95 < 1.5s (for non-fragment tools)
NFR-02: 50 concurrent without saturation
NFR-03: < 256 MB resident under steady load
TEST-05: stable memory, no PoolTimeout cascade, log growth bounded,
         daily rate-limit rollover correctly observed

No-retry contract (per 08-RESEARCH.md Open Q5):
  The driver does NOT retry on error. Failure rate IS a measurement —
  retries would mask PoolTimeout cascades and inflate apparent throughput.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import time
from pathlib import Path

import httpx
from scripts.soak.rss_sampler import (
    rss_kb_from_proc,
    rss_kb_from_remote,
    rss_kb_from_self,
)
from scripts.soak.workload import WORKLOAD


def _pick_request(rng: random.Random) -> tuple[str, dict, float]:
    """Draw one (tool_name, args, weight) entry from WORKLOAD using weighted sampling."""
    r = rng.random()
    cum = 0.0
    for tool, args, w in WORKLOAD:
        cum += w
        if r < cum:
            return (tool, args, w)
    # Fall-through: weights should sum to 1.0 but float rounding can miss;
    # return the first entry as a safe default.
    return WORKLOAD[0]


def _build_envelope(tool: str, args: dict, rng: random.Random) -> bytes:
    """Serialise a JSON-RPC 2.0 tools/call envelope."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
            "id": rng.randint(1, 1_000_000),
        }
    ).encode("utf-8")


async def _one_request(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    lat_writer: csv.writer,  # type: ignore[type-arg]
    rng: random.Random,
    soak_token: str | None,
) -> None:
    """Send a single tool-call request, categorise the outcome, and write to lat_writer.

    Rows are streamed directly to latency.csv via lat_writer rather than
    buffered in memory (WR-01: unbounded list OOM risk at high 429 rates).

    If soak_token is provided, X-Soak-Bypass: <token> is added to the request
    headers — the server's rate-limit middleware skips rate-limiting for these.

    Error categories (per 08-RESEARCH.md Open Q5):
      pool_timeout    — httpx.PoolTimeout (connection-pool exhaustion cascade signal)
      request_timeout — other httpx.TimeoutException (read/connect/write timeout)
      rate_limited    — HTTP 429 (rate-limit bucket signal)
      5xx             — server-side error
      4xx             — client-side error (unexpected in soak; indicates corpus drift)
      ok              — 2xx success
      <ExcTypeName>   — any other exception (last-resort catch)
    """
    async with sem:
        tool, args, _ = _pick_request(rng)
        payload = _build_envelope(tool, args, rng)
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
        }
        if soak_token:
            headers["x-soak-bypass"] = soak_token
        wall_ts = time.time()
        start = time.perf_counter()
        status = 0
        error_class = "ok"
        try:
            resp = await client.post("/mcp/", content=payload, headers=headers)
            status = resp.status_code
            if 200 <= resp.status_code < 300:
                error_class = "ok"
            elif resp.status_code == 429:
                error_class = "rate_limited"
            elif 500 <= resp.status_code < 600:
                error_class = "5xx"
            elif 400 <= resp.status_code < 500:
                error_class = "4xx"
            else:
                error_class = "unknown"
        except httpx.PoolTimeout:
            status = -1
            error_class = "pool_timeout"  # TEST-05: distinct flag for cascade detection
        except httpx.TimeoutException:
            status = -2
            error_class = "request_timeout"
        except Exception as exc:  # noqa: BLE001 — soak MUST log every class
            status = -3
            error_class = type(exc).__name__
        lat_writer.writerow((wall_ts, status, time.perf_counter() - start, error_class))


async def _rss_sampler_loop(
    rss_log: list,
    server_pid: int | None,
    interval_seconds: float,
    deadline_mono: float,
    *,
    metrics_client: httpx.AsyncClient | None = None,
    metrics_base_url: str | None = None,
    soak_token: str | None = None,
) -> None:
    """Sample RSS every interval_seconds until the soak deadline.

    Preference order:
      1. Remote /admin/metrics (when soak_token + metrics_base_url given) —
         the accurate path for soaks against a remote production server.
      2. /proc/{server_pid}/status (Linux, accurate SUT measurement) — local
         soak with a separate uvicorn process.
      3. resource.getrusage(RUSAGE_SELF) — samples the DRIVER, not the server.
         Last-resort fallback; rss.csv header is annotated when this is used.

    The remote path swallows errors and returns None on any failure (network
    blip, server down, token rotated). When None is returned, the sample for
    that tick is skipped rather than corrupted with a driver-self number.
    """
    use_remote = (
        metrics_client is not None and metrics_base_url is not None and bool(soak_token)
    )
    while time.monotonic() < deadline_mono:
        rss_kb: int | None
        if use_remote:
            rss_kb = await rss_kb_from_remote(
                metrics_client, metrics_base_url, soak_token  # type: ignore[arg-type]
            )
            if rss_kb is None:
                # Don't pollute the series with a driver-self sample when the
                # remote path was the intent — record a sentinel so report.py
                # can flag gaps. Using -1 keeps the CSV well-formed.
                rss_log.append((time.time(), -1))
                await asyncio.sleep(interval_seconds)
                continue
        elif server_pid is not None:
            rss_kb = rss_kb_from_proc(server_pid)
            if rss_kb is None:
                # /proc unavailable or PID gone — fall back to driver self-measurement
                rss_kb = rss_kb_from_self()
        else:
            rss_kb = rss_kb_from_self()
        rss_log.append((time.time(), rss_kb))
        await asyncio.sleep(interval_seconds)


async def run_soak(args: argparse.Namespace) -> None:
    """Main soak coroutine.

    Opens a single httpx.AsyncClient for the whole soak, bounds concurrency
    with asyncio.Semaphore, runs an RSS sidecar task, and streams latency rows
    directly to latency.csv (WR-01: avoids OOM from unbounded in-memory list).
    rss.csv is written at the end (RSS samples at 60s intervals; bounded ~1440 rows).

    Soak-bypass plumbing (remote / production runs):
      - SOAK_BYPASS_TOKEN env (set by the GHA workflow) is read once here.
      - When present, every tool-call request carries X-Soak-Bypass: <token>
        (bypasses server rate limiter) AND the RSS sampler polls
        <target>/admin/metrics for the server's resident memory.
      - When absent, behaviour is unchanged from the local-uvicorn dev path.
    """
    deadline_mono = time.monotonic() + args.duration
    rss_log: list = []
    rng = random.Random(0)  # deterministic seed for reproducibility

    # Read the soak token from env once. Don't pass via CLI — keeps it out of
    # `ps` output and shell history.
    soak_token: str | None = os.environ.get("SOAK_BYPASS_TOKEN") or None

    # Resolve server PID: --server-pid takes precedence over --server-pid-file
    server_pid: int | None = None
    if args.server_pid is not None:
        server_pid = args.server_pid
    elif args.server_pid_file is not None:
        pid_path = Path(args.server_pid_file)
        if pid_path.exists():
            try:
                server_pid = int(pid_path.read_text().strip())
            except (ValueError, OSError):
                server_pid = None

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Open latency.csv at startup and stream rows directly — avoids unbounded
    # in-memory accumulation (WR-01). The file is flushed/closed when the
    # `with` block exits (on normal completion or exception).
    with (out_dir / "latency.csv").open("w", newline="") as lat_f:
        lat_writer = csv.writer(lat_f)
        lat_writer.writerow(["wall_ts", "status", "duration_seconds", "error_class"])

        async with httpx.AsyncClient(
            base_url=args.target_url,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
        ) as client:
            sem = asyncio.Semaphore(args.concurrency)
            sampler = asyncio.create_task(
                _rss_sampler_loop(
                    rss_log,
                    server_pid,
                    args.rss_sample_interval,
                    deadline_mono,
                    metrics_client=client,
                    metrics_base_url=args.target_url,
                    soak_token=soak_token,
                )
            )
            try:
                while time.monotonic() < deadline_mono:
                    # Fire a concurrency-sized batch of requests per tick.
                    # asyncio.gather runs them in parallel up to the semaphore limit.
                    await asyncio.gather(
                        *[
                            _one_request(client, sem, lat_writer, rng, soak_token)
                            for _ in range(args.concurrency)
                        ]
                    )
            finally:
                sampler.cancel()
                try:
                    await sampler
                except asyncio.CancelledError:
                    pass

    # Write rss.csv — RSS samples at 60s intervals; max ~1440 rows over 24h (bounded).
    # Header notes the source so report.py can interpret the series correctly.
    if soak_token and not server_pid:
        rss_header_note = "rss_kb_REMOTE_ADMIN_METRICS"
    elif server_pid is not None:
        rss_header_note = "rss_kb"
    else:
        rss_header_note = "rss_kb_DRIVER_NOT_SERVER"
    with (out_dir / "rss.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wall_ts", rss_header_note])
        writer.writerows(rss_log)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="24h soak driver for mcp-zeeker (TEST-05)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=86400,
        help="Soak duration in seconds (smoke=60, full=86400)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=50,
        help="Max in-flight requests (NFR-02 = 50)",
    )
    parser.add_argument(
        "--target-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running uvicorn server",
    )
    parser.add_argument(
        "--out-dir",
        default="./soak-results",
        help="Output directory for latency.csv and rss.csv",
    )
    parser.add_argument(
        "--rss-sample-interval",
        type=float,
        default=60.0,
        help="RSS sample interval in seconds",
    )
    parser.add_argument(
        "--server-pid",
        type=int,
        default=None,
        help="PID of the uvicorn server process (for /proc/{pid}/status sampling)",
    )
    parser.add_argument(
        "--server-pid-file",
        default=None,
        help="Path to a file containing the server PID (alternative to --server-pid)",
    )
    args = parser.parse_args()
    asyncio.run(run_soak(args))


if __name__ == "__main__":
    main()
