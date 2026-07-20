#!/usr/bin/env python3
import subprocess
since = "2026-07-12 04:04:00+00"
for label, sql in [
    ("events", f"SELECT event_type, count(*) FROM events WHERE ingested_at >= '{since}' GROUP BY 1 ORDER BY 2 DESC"),
    ("alerts", f"SELECT e.event_type, count(*) FROM alerts a JOIN events e ON e.id=a.event_id WHERE a.created_at >= '{since}' GROUP BY 1"),
    ("frigate", f"""SELECT COALESCE(a.evidence_snapshot->'package'->'metadata'->>'capture_source',''),
        count(*) FROM alerts a JOIN events e ON e.id=a.event_id
        WHERE a.created_at >= '{since}' GROUP BY 1"""),
]:
    print(f"\n=== {label} ===")
    out = subprocess.check_output([
        "docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql,
    ], text=True)
    print(out)
