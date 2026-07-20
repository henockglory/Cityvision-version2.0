#!/usr/bin/env python3
import json, subprocess
SQL = """
SELECT evidence_snapshot::text FROM events
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND event_type = 'speeding'
  AND occurred_at > NOW() - INTERVAL '15 minutes'
ORDER BY occurred_at DESC LIMIT 3;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", SQL]
for line in subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines():
    snap = json.loads(line)
    pm = snap.get("package", {}).get("metadata", {})
    clip = snap.get("package", {}).get("clip", {})
    print("pts", pm.get("segment_frame_pts"), "dur", pm.get("clip_duration_sec"), "clip_size_asset", clip.get("asset_id", "")[-20:])
