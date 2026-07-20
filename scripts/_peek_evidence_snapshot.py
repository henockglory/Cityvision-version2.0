#!/usr/bin/env python3
import json, subprocess
CAM = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
sql = (
    "SELECT occurred_at::text, left(evidence_snapshot::text, 800) "
    f"FROM events WHERE event_type='speeding' AND camera_id='{CAM}' "
    "ORDER BY occurred_at DESC LIMIT 3;"
)
out = subprocess.run([
    "docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision",
    "-t", "-A", "-F", "|", "-c", sql,
], capture_output=True, text=True).stdout
for line in out.strip().splitlines():
    ts, snap_txt = line.split("|", 1)
    print("---", ts)
    try:
        snap = json.loads(snap_txt)
        print(json.dumps(snap, indent=2)[:1200])
    except Exception as e:
        print(snap_txt[:400], e)
