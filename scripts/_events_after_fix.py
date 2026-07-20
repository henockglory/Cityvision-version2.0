#!/usr/bin/env python3
import subprocess
sql = """
SELECT e.occurred_at::text, e.event_type,
       COALESCE(e.payload->>'evidence_status',''),
       COALESCE(e.payload->>'capture_source',''),
       COALESCE(e.payload->>'bbox_source',''),
       COALESCE(e.payload->>'frigate_event_id','')
FROM events e
JOIN cameras c ON c.id = e.camera_id
WHERE c.id = '8ed20433-57d5-4999-a6ab-0bea028b23a3'::uuid
  AND e.event_type = 'red_light_violation'
  AND e.occurred_at > '2026-07-11 22:46:00+00'
ORDER BY e.ingested_at DESC LIMIT 8;
"""
out = subprocess.check_output([
    "docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
], text=True)
print("events after frigate fix:")
for ln in out.splitlines():
    if ln.strip():
        print(" ", ln.replace("|", " | "))
