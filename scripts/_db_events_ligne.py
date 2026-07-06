#!/usr/bin/env python3
import subprocess, json
sql = "SELECT id, event_type, occurred_at, evidence_snapshot->'package'->'clip'->>'url' AS clip FROM events WHERE camera_id='01ee632c-271c-4e66-ba98-3d1d7e430c09' ORDER BY occurred_at DESC LIMIT 15;"
out = subprocess.check_output(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F|", "-c", sql],
    text=True,
)
print("DB events (ligne, recent):")
for line in out.strip().split("\n"):
    if not line.strip():
        continue
    parts = line.split("|")
    print(f"  {parts[2] if len(parts)>2 else ''} type={parts[1] if len(parts)>1 else ''} clip={bool(parts[3] if len(parts)>3 else '')}")
