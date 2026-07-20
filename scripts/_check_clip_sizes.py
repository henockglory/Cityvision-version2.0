#!/usr/bin/env python3
import json, os, subprocess
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
  AND occurred_at > NOW() - INTERVAL '5 minutes'
ORDER BY occurred_at DESC LIMIT 5;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", SQL]
bucket = os.environ.get("MINIO_BUCKET", "citevision-evidence")
user = os.environ.get("MINIO_ACCESS_KEY", "citevision")
secret = os.environ.get("MINIO_SECRET_KEY", "changeme_minio")
for line in subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines():
    ts, ev = line.split("\t", 1)
    snap = json.loads(ev)
    asset = snap["package"]["clip"]["asset_id"]
    script = f"mc alias set local http://127.0.0.1:9000 {user} {secret} >/dev/null 2>&1; mc stat local/{bucket}/{asset} 2>/dev/null | grep Size"
    st = subprocess.run(["docker", "exec", "citevision-v2-minio", "sh", "-c", script], capture_output=True, text=True)
    pm = snap["package"]["metadata"]
    print(ts[:19], "pts", pm.get("segment_frame_pts"), st.stdout.strip())
