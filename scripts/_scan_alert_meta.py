#!/usr/bin/env python3
import json
import subprocess

SQL = """
SELECT evidence_snapshot::text
FROM alerts
WHERE metadata->>'camera_id' = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND created_at > NOW() - INTERVAL '2 hours'
ORDER BY created_at DESC
LIMIT 20;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", SQL]
r = subprocess.run(cmd, capture_output=True, text=True)
for line in r.stdout.strip().splitlines():
    if not line.strip():
        continue
    snap = json.loads(line)
    pm = (snap.get("package") or {}).get("metadata") or {}
    keys = {k: pm.get(k) for k in (
        "capture_source", "segment_cycle_id", "segment_frame_pts", "clip_duration_sec"
    )}
    print(keys)
