#!/usr/bin/env python3
"""Dump latest evidence assets + metadata for visual inspection."""
import json
import os
import subprocess
import sys
import urllib.request

CAM = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
OUT = "/tmp/evidence_dump"
os.makedirs(OUT, exist_ok=True)

SQL = f"""
SELECT e.id::text, e.occurred_at::text, e.evidence_snapshot::text
FROM events e
WHERE e.camera_id = '{CAM}'
  AND e.event_type IN ('speeding', 'speed_exceeded', 'zone_speed')
  AND e.evidence_snapshot IS NOT NULL
ORDER BY e.occurred_at DESC
LIMIT 5;
"""
cmd = [
    "docker", "exec", "citevision-v2-postgres",
    "psql", "-U", "citevision", "-d", "citevision",
    "-t", "-A", "-F", "\t", "-c", SQL,
]
out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
if not out:
    print("NO_EVENTS")
    sys.exit(0)

for line in out.splitlines():
    eid, ts, evraw = line.split("\t", 2)
    snap = json.loads(evraw)
    pkg = snap.get("package") or {}
    meta = pkg.get("metadata") or {}
    print("\n===", ts[:19], "event", eid[:8], "===")
    print("status", meta.get("evidence_status"), "src", meta.get("capture_source"))
    print("bbox_ok", meta.get("bbox_quality_ok"), "bbox", meta.get("bbox"))
    print("frigate_emb", meta.get("frigate_bbox_embedded"), "bbox_src", meta.get("bbox_source"))
    print("subject_tex", meta.get("subject_texture"), "class", meta.get("class_name"))
    for img in pkg.get("images") or []:
        role = img.get("role")
        aid = img.get("asset_id") or ""
        url = f"http://127.0.0.1:8081/api/v1/orgs/{ORG}/assets/{aid}/content" if aid else ""
        if not url:
            continue
        dest = f"{OUT}/{ts[:19].replace(' ','_')}_{role}.jpg"
        try:
            req = urllib.request.Request(url, headers={"X-Internal-Key": "changeme_internal_service_key"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
            print(f"  {role}: {len(data)} bytes -> {dest}")
        except Exception as exc:
            print(f"  {role}: FAIL {exc}")
