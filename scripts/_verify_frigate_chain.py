#!/usr/bin/env python3
import json, subprocess, urllib.request

stats = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10).read())
print("frigate cameras:", len(stats.get("cameras") or {}))
for k, v in sorted((stats.get("cameras") or {}).items()):
    if k.startswith("cv_"):
        print(k, "cam_fps=", v.get("camera_fps"), "det=", v.get("detection_fps"))

subprocess.run(["sudo", "lsof", "-i", ":1984", "-i", ":1985", "-i", ":8554", "-i", ":8557"], check=False)

with open("/home/gheno/citevision-v2/infra/frigate-config/config.yml") as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if line.startswith("go2rtc:"):
        print("".join(lines[i : i + 12]))
        break

# recent events evidence fields
sql = """
SELECT e.occurred_at::text, e.event_type,
       COALESCE(e.payload->>'evidence_status',''),
       COALESCE(e.payload->>'capture_source',''),
       COALESCE(e.payload->>'bbox_source','')
FROM events e
JOIN cameras c ON c.id = e.camera_id
WHERE c.metadata->>'demo' = 'true'
ORDER BY e.ingested_at DESC LIMIT 8;
"""
out = subprocess.check_output([
    "docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
], text=True)
print("\nrecent demo events:")
for ln in out.splitlines():
    if ln.strip():
        print(" ", ln.replace("|", " | "))
