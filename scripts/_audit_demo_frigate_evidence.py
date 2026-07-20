#!/usr/bin/env python3
"""Audit recent demo rule evidence capture_source / bbox_source."""
from __future__ import annotations

import json
import subprocess
from collections import Counter

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
SQL = """
SELECT a.created_at::text, e.event_type, c.name,
       COALESCE(a.evidence_snapshot->'package'->'metadata'->>'capture_source',''),
       COALESCE(a.evidence_snapshot->'package'->'metadata'->>'bbox_source',''),
       COALESCE(a.evidence_snapshot->'package'->'metadata'->>'frigate_event_id','')
FROM alerts a
JOIN events e ON e.id = a.event_id
JOIN cameras c ON c.id::text = a.metadata->>'camera_id'
WHERE c.org_id = '{org}'::uuid
  AND c.metadata->>'demo' = 'true'
  AND a.created_at > NOW() - INTERVAL '6 hours'
  AND e.event_type IN ('driver_phone','seatbelt_violation','red_light_violation','speeding')
ORDER BY a.created_at DESC
LIMIT 30;
""".format(org=ORG)

cmd = [
    "docker", "exec", "citevision-v2-postgres",
    "psql", "-U", "citevision", "-d", "citevision",
    "-t", "-A", "-F", "\x1f", "-c", SQL,
]
res = subprocess.run(cmd, capture_output=True, text=True, check=False)
if res.returncode != 0:
    print("psql error:", res.stderr[:400])
    raise SystemExit(1)

rows = [ln for ln in res.stdout.splitlines() if ln.strip()]
print(f"recent demo alerts (6h): {len(rows)}")
cap = Counter()
bbox = Counter()
for ln in rows:
    parts = ln.split("\x1f")
    if len(parts) < 6:
        continue
    ts, etype, name, src, bbox_src, fe = parts[:6]
    cap[src or "unknown"] += 1
    bbox[bbox_src or "unknown"] += 1
    print(f"{ts[:19]} {etype:22} {name[:28]:28} src={src or '-':14} bbox={bbox_src or '-':16} fe={fe[:12] or '-'}")

print("\ncapture_source counts:", dict(cap))
print("bbox_source counts:", dict(bbox))