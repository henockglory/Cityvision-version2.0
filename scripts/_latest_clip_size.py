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
SELECT occurred_at::text, evidence_snapshot::text FROM events
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND event_type = 'speeding'
  AND occurred_at >= '2026-07-08 10:40:00+00'
ORDER BY occurred_at DESC LIMIT 1;
"""
raw = subprocess.run(["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", SQL], capture_output=True, text=True).stdout.strip()
if not raw:
    print("no event"); raise SystemExit(0)
ts, ev = raw.split("\t", 1)
snap = json.loads(ev)
asset = snap["package"]["clip"]["asset_id"]
pm = snap["package"]["metadata"]
bucket = os.environ.get("MINIO_BUCKET", "citevision-evidence")
user = os.environ.get("MINIO_ACCESS_KEY", "citevision")
secret = os.environ.get("MINIO_SECRET_KEY", "changeme_minio")
tmp = "/tmp/clip_check.mp4"
script = f"mc alias set local http://127.0.0.1:9000 {user} {secret} >/dev/null 2>&1; mc cat local/{bucket}/{asset} > {tmp}"
subprocess.run(["docker", "exec", "citevision-v2-minio", "sh", "-c", script])
subprocess.run(["docker", "cp", f"citevision-v2-minio:{tmp}", "/tmp/clip_check.mp4"])
sz = pathlib.Path("/tmp/clip_check.mp4").stat().st_size if pathlib.Path("/tmp/clip_check.mp4").exists() else 0
pr = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "json", "/tmp/clip_check.mp4"], capture_output=True, text=True)
print("ts", ts[:19], "pts", pm.get("segment_frame_pts"), "size", sz, "frames", pr.stdout)
