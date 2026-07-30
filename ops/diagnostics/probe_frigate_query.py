#!/usr/bin/env python3
"""Compare Frigate list query params + active-at-now for cam 108."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request


def get(url: str):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read().decode())


def active(ev, anchor, lag=90.0, grace=10.0):
    start = ev.get("start_time")
    if not isinstance(start, (int, float)):
        return False
    end = ev.get("end_time")
    if isinstance(end, (int, float)):
        return (float(start) - grace) <= anchor <= (float(end) + max(grace, lag))
    return float(start) <= (anchor + grace)


def main() -> None:
    cam = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
    now = time.time()
    for qs in (
        {"cameras": cam, "limit": 20},
        {"camera": cam, "limit": 20},
    ):
        url = "http://127.0.0.1:5000/api/events?" + urllib.parse.urlencode(qs)
        evs = get(url)
        print(f"\nquery {qs} -> n={len(evs) if isinstance(evs, list) else evs}")
        if not isinstance(evs, list):
            continue
        act = 0
        for e in evs[:10]:
            ok = active(e, now - 5)
            act += int(ok)
            print(
                str(e.get("id"))[:22],
                "start",
                e.get("start_time"),
                "end",
                e.get("end_time"),
                "active@now-5",
                ok,
                "label",
                e.get("label"),
            )
        print("active_count", act)

    # Also: events currently open anywhere
    all_e = get("http://127.0.0.1:5000/api/events?limit=30&include_thumbnails=0")
    open_n = sum(1 for e in all_e if e.get("camera") == cam and e.get("end_time") in (None, False, ""))
    print("\nopen tracks on cam", open_n)


if __name__ == "__main__":
    main()
