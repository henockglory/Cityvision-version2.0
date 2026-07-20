#!/usr/bin/env python3
import json
import subprocess

SQL = """
SELECT evidence_snapshot::text
FROM alerts
WHERE metadata->>'camera_id' = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
ORDER BY created_at DESC
LIMIT 1;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", SQL]
r = subprocess.run(cmd, capture_output=True, text=True)
raw = r.stdout.strip()
if raw:
    snap = json.loads(raw)
    print(json.dumps(snap, indent=2)[:4000])
