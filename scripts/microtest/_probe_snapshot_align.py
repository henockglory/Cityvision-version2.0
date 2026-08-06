#!/usr/bin/env python3
"""Read-only probe: quantify snapshot.frame_time vs violation anchor gap for a feu alert.

Usage: python3 _probe_snapshot_align.py [frigate_event_id] [anchor_ts]
Defaults target the last PASS alert ace66acc (event 1785997829.800832-eo5cs6).
"""
import json
import sys
import urllib.request

FRIGATE = "http://127.0.0.1:5000"
EVENT_ID = sys.argv[1] if len(sys.argv) > 1 else "1785997829.800832-eo5cs6"
# capture_frame_ts from alert ace66acc metadata (= anchor used to draw the bbox)
ANCHOR_TS = float(sys.argv[2]) if len(sys.argv) > 2 else 1785997830.860847


def main() -> int:
    url = f"{FRIGATE}/api/events/{EVENT_ID}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            ev = json.load(resp)
    except Exception as exc:
        print(f"FRIGATE_UNREACHABLE_OR_EVENT_GONE: {exc}")
        return 1

    snap = ev.get("snapshot") or {}
    data = ev.get("data") or {}
    path = data.get("path_data") or []

    snap_ft = snap.get("frame_time")
    print(f"event_id            : {EVENT_ID}")
    print(f"start_time          : {ev.get('start_time')}")
    print(f"end_time            : {ev.get('end_time')}")
    print(f"snapshot.frame_time : {snap_ft}")
    print(f"anchor_ts (bbox)    : {ANCHOR_TS}")
    if isinstance(snap_ft, (int, float)):
        delta = float(snap_ft) - ANCHOR_TS
        print(f"DELTA snapshot-anchor: {delta:+.3f} s  <-- retard/avance du bbox dessine")
    else:
        print("DELTA: snapshot.frame_time ABSENT de l'event JSON")

    print(f"path_data points    : {len(path)}")
    if path:
        ts_list = []
        for pt in path:
            try:
                ts_list.append(float(pt[1]))
            except (TypeError, ValueError, IndexError):
                continue
        if ts_list:
            print(f"path span           : {min(ts_list):.3f} .. {max(ts_list):.3f}")
            best = min(ts_list, key=lambda t: abs(t - ANCHOR_TS))
            print(f"nearest path pt to anchor : {best:.3f} (delta {best - ANCHOR_TS:+.3f} s)")
            if isinstance(snap_ft, (int, float)):
                best_s = min(ts_list, key=lambda t: abs(t - float(snap_ft)))
                print(f"nearest path pt to snap   : {best_s:.3f} (delta {best_s - float(snap_ft):+.3f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
