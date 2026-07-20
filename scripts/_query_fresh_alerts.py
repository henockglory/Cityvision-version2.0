#!/usr/bin/env python3
import json, subprocess
SQL = """
SELECT created_at::text, evidence_snapshot::text
FROM alerts
WHERE metadata->>'camera_id' = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND created_at > '2026-07-08 10:00:00+00'
ORDER BY created_at DESC LIMIT 10;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", SQL]
lines = subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()
print("count", len(lines))
for line in lines:
    ts, ev = line.split("\t", 1)
    snap = json.loads(ev) if ev != "null" else {}
    pm = (snap.get("package") or {}).get("metadata") or {}
    print(ts[:19], "src=", pm.get("capture_source"), "clip=", bool((snap.get("package") or {}).get("clip")))
