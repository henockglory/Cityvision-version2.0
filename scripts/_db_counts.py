#!/usr/bin/env python3
import subprocess
for q in [
    "SELECT event_type, count(*) FROM events WHERE camera_id='01ee632c-271c-4e66-ba98-3d1d7e430c09' GROUP BY event_type ORDER BY count DESC;",
    "SELECT count(*) FROM alerts WHERE org_id='e312f375-7442-4089-8022-ed232abc09e8';",
    "SELECT count(*), max(occurred_at) FROM events WHERE event_type='speeding';",
]:
    out = subprocess.check_output(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-c", q],
        text=True,
    )
    print(q.split("FROM")[0], "->", out.strip())
