#!/usr/bin/env python3
"""Wait for fresh frigate_track speeding events and print summary."""
from __future__ import annotations

import json
import subprocess
import sys
import time

CAM = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
WAIT = int(sys.argv[1]) if len(sys.argv) > 1 else 90


def q(sql: str) -> str:
    cmd = [
        "docker", "exec", "citevision-v2-postgres",
        "psql", "-U", "citevision", "-d", "citevision",
        "-t", "-A", "-c", sql,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()


print(f"==> waiting {WAIT}s for new events...")
time.sleep(WAIT)
rows = q(
    "SELECT evidence_snapshot::text FROM events "
    f"WHERE event_type='speeding' AND camera_id='{CAM}' "
    "ORDER BY occurred_at DESC LIMIT 15;"
).splitlines()
ft = 0
live = 0
for line in rows:
    if not line or line == "null":
        continue
    try:
        snap = json.loads(line)
    except json.JSONDecodeError:
        continue
    meta = (snap.get("package") or {}).get("metadata") or {}
    src = meta.get("capture_source") or "unknown"
    if src == "frigate_track":
        ft += 1
    elif src == "live":
        live += 1
    print(
        f"  src={src} status={meta.get('evidence_status')} "
        f"frigate_id={meta.get('frigate_event_id')} bbox_ok={meta.get('bbox_quality_ok')}"
    )
print(json.dumps({"frigate_track": ft, "live": live, "sampled": len(rows)}, indent=2))
