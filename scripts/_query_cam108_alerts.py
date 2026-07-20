#!/usr/bin/env python3
"""Query cam108 alerts from postgres."""
import json
import subprocess

SQL = """
SELECT id,
       metadata->>'capture_source' AS capture_source,
       evidence_snapshot::text,
       created_at::text
FROM alerts
WHERE metadata->>'camera_id' = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
ORDER BY created_at DESC
LIMIT 15;
"""
cmd = [
    "docker", "exec", "citevision-v2-postgres",
    "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "|", "-c", SQL,
]
r = subprocess.run(cmd, capture_output=True, text=True)
for line in r.stdout.strip().splitlines():
    parts = line.split("|", 3)
    if len(parts) < 4:
        print(line)
        continue
    aid, src, ev, ts = parts
    print(f"id={aid[:8]}… src={src} ts={ts}")
    if ev and ev != "null":
        try:
            snap = json.loads(ev)
            pkg = snap.get("package") or {}
            pm = pkg.get("metadata") or {}
            clip = (pkg.get("clip") or {}).get("url", "")
            print(f"  pkg_src={pm.get('capture_source')} clip={clip[:80]}")
        except json.JSONDecodeError:
            print("  (evidence parse error)")
