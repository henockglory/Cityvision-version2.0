#!/usr/bin/env python3
"""Measure Frigate event creation → end_time delay (Sprint 1 remédiation §5).

Polls Frigate /api/events and records how long each event takes to gain end_time.
Use the p50/p95/p99 to calibrate frigate_red_light_end_time_wait_sec.

Usage (WSL):
  python3 scripts/measure_frigate_end_time.py --seconds 120 --camera cv_<uuid>
  python3 scripts/measure_frigate_end_time.py --seconds 180   # all cameras
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _get_json(url: str, timeout: float = 8.0) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frigate", default="http://127.0.0.1:5000")
    ap.add_argument("--camera", default="", help="Frigate camera id (e.g. cv_<uuid>)")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    seen_start: dict[str, float] = {}  # event_id -> wall when first seen without end_time
    sealed: list[float] = []  # delays sec
    deadline = time.time() + args.seconds
    print(f"measuring Frigate end_time delays for {args.seconds:.0f}s at {args.frigate}", flush=True)

    while time.time() < deadline:
        qs: dict[str, Any] = {"limit": args.limit}
        if args.camera:
            qs["cameras"] = args.camera
        url = f"{args.frigate.rstrip('/')}/api/events?{urllib.parse.urlencode(qs)}"
        events = _get_json(url)
        if not isinstance(events, list):
            time.sleep(args.poll)
            continue
        now = time.time()
        for ev in events:
            if not isinstance(ev, dict):
                continue
            eid = str(ev.get("id") or "")
            if not eid:
                continue
            end = ev.get("end_time")
            if end in (None, "", False):
                seen_start.setdefault(eid, now)
                continue
            if eid in seen_start:
                sealed.append(now - seen_start.pop(eid))
            # Also sample completed events via start_time → end_time span if available
            start = ev.get("start_time")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                span = float(end) - float(start)
                if 0 < span < 600:
                    # store as negative sentinel? no — keep only observed seal delays
                    pass
        time.sleep(args.poll)

    sealed.sort()
    print(f"sealed_samples={len(sealed)} still_open={len(seen_start)}", flush=True)
    if sealed:
        print(
            f"delay_sec p50={_percentile(sealed, 50):.2f} "
            f"p95={_percentile(sealed, 95):.2f} "
            f"p99={_percentile(sealed, 99):.2f} "
            f"max={sealed[-1]:.2f} mean={statistics.mean(sealed):.2f}",
            flush=True,
        )
        recommend = max(15.0, _percentile(sealed, 95) * 1.25)
        print(f"recommend frigate_red_light_end_time_wait_sec >= {recommend:.1f}", flush=True)
    else:
        print(
            "no seal delays observed — leave events open longer, or pass --camera with live traffic",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
