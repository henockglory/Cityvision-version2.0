#!/usr/bin/env python3
import subprocess

queries = [
    ("events frigate_track", "SELECT count(*), max(ingested_at)::text FROM events WHERE payload->>'capture_source' = 'frigate_track';"),
    ("events complete", "SELECT count(*), max(ingested_at)::text FROM events WHERE payload->>'evidence_status' = 'complete';"),
    ("alerts total", "SELECT count(*), max(created_at)::text FROM alerts;"),
    ("frigate cameras in config", "SELECT count(*) FROM cameras WHERE metadata->>'demo' = 'true';"),
]
for label, sql in queries:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True,
    )
    print(f"{label}: {(r.stdout or r.stderr).strip()}")
