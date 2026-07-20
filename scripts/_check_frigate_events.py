#!/usr/bin/env python3
import json, subprocess, urllib.request

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"

# Frigate events
try:
    ev = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:5000/api/events?limit=10&camera=cv_8ed20433-57d5-4999-a6ab-0bea028b23a3",
        timeout=10,
    ).read())
    print("frigate events (feux):", len(ev))
    for e in ev[:5]:
        print(" ", e.get("id", "")[:12], e.get("label"), e.get("camera"))
except Exception as exc:
    print("frigate events error:", exc)

sql = f"""
SELECT e.occurred_at::text, e.event_type,
       COALESCE(e.payload->>'evidence_status',''),
       COALESCE(e.payload->>'capture_source',''),
       COALESCE(e.payload->>'bbox_source',''),
       COALESCE(e.payload->>'frigate_event_id','')
FROM events e
JOIN cameras c ON c.id = e.camera_id
WHERE c.org_id = '{ORG}'::uuid
  AND e.event_type IN ('red_light_violation','speeding','driver_phone','seatbelt_violation')
ORDER BY e.ingested_at DESC
LIMIT 10;
"""
out = subprocess.check_output([
    "docker", "exec", "citevision-v2-postgres",
    "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
], text=True)
print("\nrule events:")
for ln in out.splitlines():
    if ln.strip():
        print(" ", ln.replace("|", " | "))

sql2 = f"""
SELECT active_video_id::text FROM org_demo_settings WHERE org_id='{ORG}'::uuid;
"""
print("\nactive_video:", subprocess.check_output([
    "docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql2,
], text=True).strip())
