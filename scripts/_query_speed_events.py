#!/usr/bin/env python3
import json, subprocess
SQL = """
SELECT occurred_at::text, evidence_snapshot::text
FROM events
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND event_type = 'speeding'
ORDER BY occurred_at DESC LIMIT 8;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", SQL]
for line in subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines():
    ts, ev = line.split("\t", 1)
    snap = json.loads(ev) if ev != "null" else {}
    pm = (snap.get("package") or {}).get("metadata") or {}
    print(ts[:19], "src=", pm.get("capture_source"), "seg=", pm.get("segment_cycle_id"), "clip=", bool((snap.get("package") or {}).get("clip")))
