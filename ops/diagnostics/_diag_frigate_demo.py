#!/usr/bin/env python3
"""Diagnose demo video + Frigate evidence chain."""
from __future__ import annotations

import json
import subprocess
import urllib.request

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"


def curl_json(url: str) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  FAIL {url}: {e}")
        return None


def psql(sql: str) -> str:
    cmd = [
        "docker", "exec", "citevision-v2-postgres",
        "psql", "-U", "citevision", "-d", "citevision",
        "-t", "-A", "-c", sql,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        print("psql error:", res.stderr[:500])
        return ""
    return res.stdout.strip()


print("=== .env Frigate / evidence ===")
for line in open("/home/gheno/citevision-v2/.env", encoding="utf-8", errors="replace"):
    if any(k in line for k in ("FRIGATE_", "EVIDENCE_BACKEND", "GO2RTC")):
        print(line.rstrip())

print("\n=== Demo active video ===")
print(psql(
    f"SELECT active_video_id::text, active_go2rtc_src FROM org_demo_settings WHERE org_id='{ORG}'::uuid;"
))

print("\n=== Demo videos / cameras ===")
print(psql(
    f"""SELECT dv.name, dv.go2rtc_src, c.name, c.id::text
        FROM org_demo_videos dv
        LEFT JOIN cameras c ON c.metadata->>'demo_video_id' = dv.id::text AND c.org_id = dv.org_id
        WHERE dv.org_id = '{ORG}'::uuid
        ORDER BY dv.name;"""
))

print("\n=== go2rtc demo streams ===")
streams = curl_json("http://127.0.0.1:1984/api/streams")
if isinstance(streams, dict):
    for k in sorted(streams):
        if k.startswith("demo-"):
            print(f"  {k}: {streams[k]}")

print("\n=== Frigate camera fps ===")
stats = curl_json("http://127.0.0.1:5000/api/stats")
if isinstance(stats, dict):
    cams = stats.get("cameras") or {}
    print(f"  cameras: {len(cams)}")
    for k, v in sorted(cams.items()):
        if k.startswith("cv_"):
            print(
                f"  {k}: camera_fps={v.get('camera_fps',0)} "
                f"detect_fps={v.get('detection_fps',0)}"
            )

print("\n=== Frigate config upstream paths (demo) ===")
try:
    with open("/home/gheno/citevision-v2/infra/frigate-config/config.yml", encoding="utf-8") as f:
        for line in f:
            if "rtsp://" in line and ("demo-" in line or "8554" in line):
                print(" ", line.rstrip())
except FileNotFoundError:
    print("  config.yml missing")

print("\n=== Recent demo events (payload fields) ===")
sql = f"""
SELECT e.created_at::text, e.event_type, c.name,
       COALESCE(e.payload->>'evidence_status',''),
       COALESCE(e.payload->>'capture_source',''),
       COALESCE(e.payload->>'bbox_source',''),
       COALESCE(e.payload->'evidence'->>'status','')
FROM events e
JOIN cameras c ON c.id = e.camera_id
WHERE c.org_id = '{ORG}'::uuid
  AND c.metadata->>'demo' = 'true'
  AND e.created_at > NOW() - INTERVAL '6 hours'
ORDER BY e.created_at DESC
LIMIT 15;
"""
for ln in psql(sql).splitlines():
    if ln.strip():
        print(" ", ln.replace("|", " | "))

print("\n=== Recent demo alerts ===")
sql2 = f"""
SELECT a.created_at::text, e.event_type,
       COALESCE(a.evidence_snapshot->'package'->'metadata'->>'capture_source',''),
       COALESCE(a.evidence_snapshot->'package'->'metadata'->>'bbox_source','')
FROM alerts a
JOIN events e ON e.id = a.event_id
JOIN cameras c ON c.id::text = a.metadata->>'camera_id'
WHERE c.org_id = '{ORG}'::uuid
  AND c.metadata->>'demo' = 'true'
  AND a.created_at > NOW() - INTERVAL '6 hours'
ORDER BY a.created_at DESC
LIMIT 10;
"""
rows = [ln for ln in psql(sql2).splitlines() if ln.strip()]
print(f"  count: {len(rows)}")
for ln in rows:
    print(" ", ln.replace("|", " | "))
