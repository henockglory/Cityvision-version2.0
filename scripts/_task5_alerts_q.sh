#!/usr/bin/env bash
python3 - <<'PY'
import subprocess, json
sql = r'''
SELECT a.id::text,
  a.created_at,
  a.title,
  a.evidence_snapshot->>'capture_source' AS cap,
  a.evidence_snapshot->>'evidence_status' AS es1,
  a.metadata->>'evidence_status' AS es2,
  a.evidence_snapshot->'metadata'->>'demo_loop_position_sec' AS loop_pos,
  a.evidence_snapshot->'metadata'->>'demo_loop_duration_sec' AS loop_dur,
  a.evidence_snapshot->'metadata'->>'capture_source' AS cap2,
  LEFT(COALESCE(a.evidence_snapshot::text,''), 180) AS snap_head
FROM alerts a
WHERE a.created_at > NOW() - INTERVAL '6 hours'
ORDER BY a.created_at DESC
LIMIT 25;
'''
r = subprocess.run(
  ["docker","exec","-i","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-c",sql],
  capture_output=True, text=True
)
print(r.stdout)
if r.stderr: print("ERR", r.stderr[:400])

sql2 = r'''
SELECT
  COUNT(*) FILTER (WHERE evidence_snapshot->>'capture_source' = 'demo_ring_buffer'
    OR evidence_snapshot->'metadata'->>'capture_source' = 'demo_ring_buffer') AS ring,
  COUNT(*) FILTER (WHERE COALESCE(evidence_snapshot->>'evidence_status', metadata->>'evidence_status') = 'complete') AS complete,
  COUNT(*) AS total_alerts
FROM alerts
WHERE created_at > NOW() - INTERVAL '6 hours'
  AND (title ILIKE '%feu%' OR title ILIKE '%red%' OR evidence_snapshot::text ILIKE '%red_light%' OR metadata::text ILIKE '%red_light%');
'''
r = subprocess.run(
  ["docker","exec","-i","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-c",sql2],
  capture_output=True, text=True
)
print("COUNTS", r.stdout)
PY
