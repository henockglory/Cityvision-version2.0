#!/usr/bin/env python3
import subprocess

CAM = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
MARKER = "2026-07-08 07:04:41+00"

sql = f"""
SELECT a.created_at, a.title, e.payload->>'speed_kmh' as speed,
       (a.metadata->'package' IS NOT NULL) as has_pkg
FROM alerts a
JOIN events e ON e.id = a.event_id
WHERE e.camera_id = '{CAM}' AND e.event_type = 'speeding'
ORDER BY a.created_at DESC LIMIT 8;
"""
print("=== Dernières alertes speeding ===")
proc = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
    capture_output=True, text=True,
)
print(proc.stdout or proc.stderr)

sql2 = f"""
SELECT count(*) as alerts_since_marker
FROM alerts a JOIN events e ON e.id=a.event_id
WHERE e.camera_id='{CAM}' AND e.event_type='speeding' AND a.created_at > '{MARKER}';
"""
proc2 = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql2],
    capture_output=True, text=True,
)
print("=== Alertes depuis limite 1 km/h ===")
print(proc2.stdout or proc2.stderr)
