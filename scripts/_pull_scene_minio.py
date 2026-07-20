#!/usr/bin/env python3
"""Download latest complete evidence scene from MinIO for visual check."""
import json
import subprocess
import sys

CAM = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
SQL = f"""
SELECT e.evidence_snapshot::text
FROM events e
WHERE e.camera_id = '{CAM}'
  AND e.event_type = 'speeding'
  AND e.evidence_snapshot::text LIKE '%complete%'
ORDER BY e.occurred_at DESC
LIMIT 1;
"""
out = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", SQL],
    capture_output=True, text=True,
).stdout.strip()
if not out:
    print("NO_COMPLETE")
    sys.exit(1)
snap = json.loads(out)
pkg = snap.get("package") or {}
meta = pkg.get("metadata") or {}
scene = next((i for i in (pkg.get("images") or []) if i.get("role") == "scene"), None)
aid = (scene or {}).get("asset_id") or ""
if not aid:
    print("NO_SCENE_ASSET")
    sys.exit(1)
# MinIO path: bucket citevision-evidence, key = asset_id
key = aid
cmd = ["docker", "exec", "citevision-v2-minio", "mc", "cp", f"local/citevision-evidence/{key}", "/tmp/scene_check.jpg"]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    # try aws cli style via python boto in minio - fallback curl minio API
    print("mc_fail", r.stderr[:200])
    sys.exit(2)
subprocess.run(["docker", "cp", "citevision-v2-minio:/tmp/scene_check.jpg", "/tmp/scene_check.jpg"], check=True)
print("bbox", meta.get("bbox"), "source", meta.get("bbox_source"), "emb", meta.get("frigate_bbox_embedded"))
print("saved", "/tmp/scene_check.jpg")
