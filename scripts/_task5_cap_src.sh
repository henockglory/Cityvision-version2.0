#!/usr/bin/env bash
python3 - <<'PY'
import subprocess, json
sql = r'''
SELECT a.id::text,
  a.created_at,
  a.evidence_snapshot->'package'->>'capture_source' AS pkg_cap,
  a.evidence_snapshot->'package'->'metadata'->>'capture_source' AS meta_cap,
  a.evidence_snapshot->'package'->'metadata'->>'demo_loop_position_sec' AS loop_pos,
  a.evidence_snapshot->'package'->'metadata'->>'demo_loop_duration_sec' AS loop_dur,
  a.evidence_snapshot->'package'->>'evidence_status' AS pkg_es,
  a.metadata->>'evidence_status' AS meta_es,
  a.evidence_snapshot->'package'->'metadata'->>'plate_status' AS plate
FROM alerts a
WHERE a.created_at > NOW() - INTERVAL '6 hours'
  AND a.title ILIKE '%Feu%'
ORDER BY a.created_at DESC;
'''
r = subprocess.run(
  ["docker","exec","-i","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-c",sql],
  capture_output=True, text=True
)
print(r.stdout)
# one full package metadata
sql2 = r'''
SELECT jsonb_pretty(evidence_snapshot->'package'->'metadata')
FROM alerts WHERE id='2d825076-9cb3-4211-a52f-7bb552ca5fd3';
'''
r = subprocess.run(
  ["docker","exec","-i","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-c",sql2],
  capture_output=True, text=True
)
print("META", r.stdout[:2000])
PY
