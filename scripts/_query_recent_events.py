#!/usr/bin/env python3
import subprocess
SQL = """
SELECT occurred_at::text, event_type, evidence_snapshot::text
FROM events
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
ORDER BY occurred_at DESC LIMIT 5;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", SQL]
import json
for line in subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines():
    parts = line.split("\t", 2)
    if len(parts) < 3:
        continue
    ts, et, ev = parts
    snap = json.loads(ev) if ev and ev != "null" else {}
    pm = (snap.get("package") or {}).get("metadata") or {}
    print(ts, et, "capture_source=", pm.get("capture_source"), "clip=", bool((snap.get("package") or {}).get("clip")))
