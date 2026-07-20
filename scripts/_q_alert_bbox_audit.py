#!/usr/bin/env python3
import subprocess

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
sql = f"""
SELECT r.name,
  a.evidence_snapshot->'package'->'metadata'->>'align_delta_ms',
  a.evidence_snapshot->'package'->'metadata'->>'bbox_quality_ok',
  a.evidence_snapshot->'package'->'metadata'->>'frigate_event_id',
  a.evidence_snapshot->'package'->'metadata'->'bbox',
  a.evidence_snapshot->>'class_name',
  a.evidence_snapshot->'bbox'
FROM alerts a
JOIN rules r ON r.id = a.rule_id
WHERE a.org_id = '{ORG}'::uuid
ORDER BY a.created_at DESC
LIMIT 5;
"""
cmd = [
    "docker", "exec", "citevision-v2-postgres",
    "psql", "-U", "citevision", "-d", "citevision", "-c", sql,
]
subprocess.run(cmd)
