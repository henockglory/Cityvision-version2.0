#!/usr/bin/env python3
import json, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (Path.home() / "citevision-v2" / ".env",):
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SQL = """
SELECT evidence_snapshot::text FROM events
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND event_type = 'speeding'
ORDER BY occurred_at DESC LIMIT 1;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", SQL]
raw = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
snap = json.loads(raw)
asset = snap["package"]["clip"]["asset_id"]
print("asset", asset)
bucket = os.environ.get("MINIO_BUCKET", "citevision-evidence")
user = os.environ.get("MINIO_ACCESS_KEY", "citevision")
secret = os.environ.get("MINIO_SECRET_KEY", "changeme_minio")
tmp = "/tmp/cv_test_clip.mp4"
script = f"mc alias set local http://127.0.0.1:9000 {user} {secret} && mc stat local/{bucket}/{asset} && mc cat local/{bucket}/{asset} > {tmp}"
r = subprocess.run(["docker", "exec", "citevision-v2-minio", "sh", "-c", script], capture_output=True, text=True)
print("docker", r.returncode, r.stderr[-500:] if r.stderr else r.stdout[:200])
subprocess.run(["docker", "cp", f"citevision-v2-minio:{tmp}", "/tmp/cv_test_clip.mp4"], check=False)
p = Path("/tmp/cv_test_clip.mp4")
print("local size", p.stat().st_size if p.exists() else 0)
if p.exists():
    pr = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "json", str(p)], capture_output=True, text=True)
    print("ffprobe", pr.stdout)
