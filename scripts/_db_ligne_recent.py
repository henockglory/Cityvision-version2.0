#!/usr/bin/env python3
import subprocess
sql = """SELECT event_type, occurred_at, left(id::text,8),
  evidence_snapshot->'package'->'clip'->>'url' IS NOT NULL AS has_clip,
  jsonb_array_length(COALESCE(evidence_snapshot->'package'->'images','[]'::jsonb)) AS nimg
FROM events WHERE camera_id='01ee632c-271c-4e66-ba98-3d1d7e430c09'
ORDER BY occurred_at DESC LIMIT 10;"""
print(subprocess.check_output(
    ["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-c",sql], text=True))
