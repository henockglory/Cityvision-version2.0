#!/usr/bin/env python3
"""Probe why zone_ok=True but active=False for Frigate fallback."""
from __future__ import annotations

import json
import time
import urllib.request


def http_json(url: str):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read().decode())


def active_at(ev, anchor, grace=2.0, max_open=180.0, max_end_lag=30.0):
    start = ev.get("start_time")
    if not isinstance(start, (int, float)):
        return False, "no_start"
    start_f = float(start)
    end = ev.get("end_time")
    if isinstance(end, (int, float)):
        end_f = float(end)
        ok = (start_f - grace) <= float(anchor) <= (end_f + max(grace, max_end_lag))
        return ok, f"sealed start={start_f:.1f} end={end_f:.1f} lag_need={float(anchor)-end_f:.1f}"
    now = time.time()
    if (now - start_f) > max_open and (float(anchor) - start_f) > max_open:
        return False, f"open_ancient age_now={now-start_f:.1f} age_anchor={float(anchor)-start_f:.1f}"
    ok = start_f <= (float(anchor) + grace)
    return ok, f"open start={start_f:.1f} start_minus_anchor={start_f-float(anchor):.1f}"


def main() -> None:
    now = time.time()
    print(f"now={now:.3f}")
    stats = http_json("http://127.0.0.1:5000/api/stats")
    cams = list((stats.get("cameras") or {}).keys())
    print("cams", cams)
    for cam in cams:
        events = http_json(
            f"http://127.0.0.1:5000/api/events?camera={cam}&limit=15&include_thumbnails=0"
        )
        print(f"\n=== {cam} ({len(events) if isinstance(events, list) else '?'}) ===")
        if not isinstance(events, list):
            continue
        # Use a recent IA-like anchor = now - 5s
        for anchor_label, anchor in [("now-5", now - 5), ("now-30", now - 30), ("now-120", now - 120)]:
            print(f"-- anchor {anchor_label}={anchor:.3f} --")
            for e in events[:8]:
                data = e.get("data") or {}
                ok, why = active_at(e, anchor)
                print(
                    str(e.get("id", ""))[:20],
                    e.get("label"),
                    "active",
                    ok,
                    why,
                    "box",
                    data.get("box"),
                )


if __name__ == "__main__":
    main()
