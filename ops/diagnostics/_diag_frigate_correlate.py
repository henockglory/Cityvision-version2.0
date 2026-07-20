#!/usr/bin/env python3
"""One-shot Frigate correlation diagnostic for latest speeding event."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/gheno/citevision-v2")
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence  # noqa: E402

CAM = "55694d53-8f58-4981-91b2-7c6cd528a25d"


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    return (r.stdout or "").strip()


def main() -> None:
    raw = psql(
        "SELECT payload::text FROM events WHERE event_type='speeding' "
        "ORDER BY ingested_at DESC LIMIT 1;"
    )
    if not raw:
        print("no speeding events")
        return
    meta = json.loads(raw)
    evt = {
        "class_name": meta.get("class_name"),
        "bbox": meta.get("bbox"),
        "bbox_ts": meta.get("bbox_ts"),
        "event_id": "diag",
    }
    print(f"evt class={evt.get('class_name')} bbox_ts={evt.get('bbox_ts')} bbox={evt.get('bbox')}")

    ft = FrigateTrackEvidence()
    fid = ft.frigate_camera_id(CAM)
    events = ft._list_events(fid)
    print(f"frigate events={len(events)} camera={fid}")
    if events:
        e0 = events[0]
        print(f"  latest id={e0.get('id')} start={e0.get('start_time')} label={e0.get('label')}")
        data = e0.get("data") if isinstance(e0.get("data"), dict) else {}
        print(f"  box={data.get('box')}")

    anchor = float(evt.get("bbox_ts") or 0)
    matched, delta = ft._correlate_event(fid, anchor, evt, camera_id=CAM)
    print(f"correlate matched={matched.get('id') if matched else None} delta={delta:.2f}")

    # Replay anchors from failed test window (strict pass-1 miss, demo passes should recover).
    for test_anchor in (1783864211.555, 1783864219.152, anchor):
        m2, d2 = ft._correlate_event(fid, test_anchor, evt, camera_id=CAM)
        print(f"  anchor={test_anchor:.3f} -> matched={bool(m2)} delta={d2:.2f}")


if __name__ == "__main__":
    main()
