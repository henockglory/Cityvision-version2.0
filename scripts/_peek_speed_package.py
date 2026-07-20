#!/usr/bin/env python3
import subprocess, json
sql = """
SELECT payload->'package' as pkg, payload->>'evidence_status' as es
FROM events WHERE event_type='speeding' AND ingested_at > now() - interval '20 minutes'
AND payload ? 'package'
ORDER BY ingested_at DESC LIMIT 1;
"""
r = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
    capture_output=True, text=True,
)
line = (r.stdout or "").strip()
if not line:
    print("no package events")
    raise SystemExit(0)
pkg_raw, es = line.split("|", 1)
pkg = json.loads(pkg_raw)
print("evidence_status=", es)
print("clip=", pkg.get("clip"))
imgs = pkg.get("images") or []
print("images=", json.dumps(imgs, indent=2)[:800])
meta = pkg.get("metadata") or {}
print("capture_source=", meta.get("capture_source"))
print("evidence_status meta=", meta.get("evidence_status"))
print("bbox_quality_ok=", meta.get("bbox_quality_ok"))
print("missing_roles=", meta.get("missing_roles"))
