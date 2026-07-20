#!/usr/bin/env python3
import json, subprocess
SQL = """
SELECT occurred_at::text, evidence_snapshot::text FROM events
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND event_type = 'speeding'
  AND occurred_at > '2026-07-08 10:34:00+00'
ORDER BY occurred_at DESC LIMIT 3;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", SQL]
for line in subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines():
    ts, ev = line.split("\t", 1)
    snap = json.loads(ev)
    clip = snap.get("package", {}).get("clip", {})
    pm = snap.get("package", {}).get("metadata", {})
    print(ts[:19], "asset", clip.get("asset_id", "")[-36:], "dur", pm.get("clip_duration_sec"), "status", pm.get("evidence_status"))
