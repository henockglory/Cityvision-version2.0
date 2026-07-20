#!/usr/bin/env bash
set -uo pipefail
cd /home/gheno/citevision-v2
# Recent red_light alerts + evidence meta
python3 - <<'PY'
import json, os, subprocess
# use psql via docker
sql = r'''
SELECT a.id::text, a.created_at,
  a.metadata->>'evidence_status' AS evid_status,
  a.metadata->'evidence_package'->>'capture_source' AS cap_src,
  a.metadata->'evidence_package'->'metadata'->>'capture_source' AS cap_src2,
  a.metadata->'evidence_package'->'metadata'->>'demo_loop_position_sec' AS loop_pos,
  a.metadata->'evidence_package'->'metadata'->>'demo_loop_duration_sec' AS loop_dur,
  a.metadata->>'plate_status' AS plate_status,
  LEFT(COALESCE(a.metadata::text,''), 200) AS meta_head
FROM alerts a
WHERE a.created_at > NOW() - INTERVAL '3 hours'
  AND (
    a.metadata::text ILIKE '%red_light%'
    OR a.event_type = 'red_light_violation'
    OR a.rule_name ILIKE '%Feu%'
  )
ORDER BY a.created_at DESC
LIMIT 20;
'''
# discover columns
sql2 = r'''
SELECT column_name FROM information_schema.columns
WHERE table_name='alerts' ORDER BY ordinal_position;
'''
r = subprocess.run(
  ["docker","exec","-i","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",sql2],
  capture_output=True, text=True
)
print("cols:", r.stdout.strip().splitlines())
print("err:", r.stderr[:300] if r.stderr else "")

# simpler query
sql3 = r'''
SELECT id::text, created_at, event_type,
  metadata->>'evidence_status' AS es,
  COALESCE(
    metadata->'package'->>'capture_source',
    metadata->'evidence'->>'capture_source',
    metadata->'evidence_snapshot'->>'capture_source',
    metadata->>'capture_source'
  ) AS cs,
  LEFT(metadata::text, 400) AS head
FROM alerts
WHERE created_at > NOW() - INTERVAL '4 hours'
ORDER BY created_at DESC
LIMIT 15;
'''
r = subprocess.run(
  ["docker","exec","-i","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-c",sql3],
  capture_output=True, text=True
)
print(r.stdout)
print(r.stderr[:500] if r.stderr else "")
PY

echo "=== AI abort-stats (sample) ==="
curl -sf http://127.0.0.1:8001/evidence/abort-stats 2>/dev/null | python3 -m json.tool 2>/dev/null | head -60 || true

echo "=== T6 log skip reload today ==="
grep -a 'frigate config unchanged' /home/gheno/citevision-v2/logs/backend.log | tail -5

echo "=== config record permanent ==="
python3 - <<'PY'
from pathlib import Path
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
print("record enabled true:", text.count("record:\n      enabled: true") or text.count("record:"))
for line in text.splitlines():
    if "record:" in line or "snapshots:" in line or line.strip().startswith("enabled:"):
        if True:
            pass
# count per cam
import re
cams=re.findall(r'(cv_[a-f0-9-]+):', text)
print("cams", cams)
print("record.enabled true count", len(re.findall(r'record:\n\s+enabled:\s*true', text)))
print("snapshots.enabled true count", len(re.findall(r'snapshots:\n\s+enabled:\s*true', text)))
PY
