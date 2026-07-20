#!/usr/bin/env python3
"""Inspect latest speeding evidence for camera 108."""
import json
import subprocess

CAM = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
SQL = f"""
SELECT e.occurred_at::text, e.event_type, e.evidence_snapshot::text
FROM events e
WHERE e.camera_id = '{CAM}'
  AND e.event_type IN ('speeding', 'speed_exceeded', 'zone_speed')
ORDER BY e.occurred_at DESC
LIMIT 10;
"""
cmd = [
    "docker", "exec", "citevision-v2-postgres",
    "psql", "-U", "citevision", "-d", "citevision",
    "-t", "-A", "-F", "\t", "-c", SQL,
]
out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
if not out:
    print("NO_EVENTS")
    raise SystemExit(0)
for line in out.splitlines():
    parts = line.split("\t", 2)
    if len(parts) < 3:
        continue
    ts, etype, evraw = parts[0], parts[1], parts[2]
    snap = json.loads(evraw) if evraw and evraw != "null" else {}
    pkg = snap.get("package") or {}
    meta = pkg.get("metadata") or {}
    clip = pkg.get("clip") or {}
    imgs = pkg.get("images") or []
    print(
        ts[:19],
        etype,
        "src=", meta.get("capture_source"),
        "bbox_src=", meta.get("bbox_source"),
        "frigate_emb=", meta.get("frigate_bbox_embedded"),
        "bbox_ok=", meta.get("bbox_quality_ok"),
        "status=", meta.get("evidence_status"),
        "clip=", bool(clip.get("asset_id") or clip.get("url")),
        "scene=", any(i.get("role") == "scene" for i in imgs),
        "subject=", any(i.get("role") == "subject" for i in imgs),
    )
