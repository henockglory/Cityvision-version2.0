#!/usr/bin/env python3
import json, subprocess, pathlib, os
from pathlib import Path
for p in (Path.home() / "citevision-v2" / ".env",):
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
SQL = """
SELECT occurred_at::text, evidence_snapshot::text
FROM events
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND event_type = 'speeding'
ORDER BY occurred_at DESC LIMIT 1;
"""
raw = subprocess.run(["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", SQL], capture_output=True, text=True).stdout.strip()
ts, ev = raw.split("\t", 1)
snap = json.loads(ev)
pm = snap.get("package", {}).get("metadata", {})
clip = snap.get("package", {}).get("clip", {})
print("ts", ts[:22])
print("capture_source", pm.get("capture_source"))
print("segment_pts", pm.get("segment_frame_pts"))
print("clip_dur", pm.get("clip_duration_sec"))
print("asset", clip.get("asset_id", "")[-45:])
bucket = os.environ.get("MINIO_BUCKET", "citevision-evidence")
user = os.environ.get("MINIO_ACCESS_KEY", "citevision")
secret = os.environ.get("MINIO_SECRET_KEY", "changeme_minio")
tmp = "/tmp/x.mp4"
script = f"mc alias set local http://127.0.0.1:9000 {user} {secret} >/dev/null 2>&1; mc cat local/{bucket}/{clip.get('asset_id')} > {tmp}"
subprocess.run(["docker", "exec", "citevision-v2-minio", "sh", "-c", script])
subprocess.run(["docker", "cp", f"citevision-v2-minio:{tmp}", "/tmp/x.mp4"])
print("size", pathlib.Path("/tmp/x.mp4").stat().st_size if pathlib.Path("/tmp/x.mp4").exists() else 0)
