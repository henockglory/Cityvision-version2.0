#!/usr/bin/env python3
import json
import subprocess
import sys

eid = sys.argv[1] if len(sys.argv) > 1 else "ff4e8617-e7f3-48c1-a33b-dd77b1a0423c"
sql = f"SELECT evidence_snapshot::text, payload::text FROM events WHERE id='{eid}';"
r = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "|", "-c", sql],
    capture_output=True,
    text=True,
)
parts = r.stdout.strip().split("|", 1)
snap = json.loads(parts[0])
payload = json.loads(parts[1]) if len(parts) > 1 and parts[1] else {}
pkg = snap.get("package", {})
meta = pkg.get("metadata", {})
imgs = pkg.get("images", [])
for k in ("evidence_status", "bbox_source", "bbox_quality_ok", "subject_quality_ok", "subject_texture", "capture_frame_ts", "bbox_ts", "track_id"):
    print(k, meta.get(k))
print("images", [(i.get("role"), i.get("asset_id")) for i in imgs])
print("payload_track_id", payload.get("track_id"))
