#!/usr/bin/env python3
import subprocess

queries = [
    "SELECT count(1) FROM events WHERE camera_id='726ff8a1-8442-4bdb-96ad-ec40a2fbb424';",
    "SELECT event_type, count(1) FROM events WHERE camera_id='726ff8a1-8442-4bdb-96ad-ec40a2fbb424' GROUP BY 1 ORDER BY 2 DESC LIMIT 15;",
    "SELECT event_type, count(1) FROM events WHERE camera_id='01ee632c-271c-4e66-ba98-3d1d7e430c09' GROUP BY 1 ORDER BY 2 DESC LIMIT 15;",
    "SELECT event_type, payload->>'demo' AS demo, count(1) FROM events WHERE event_type IN ('phone_driving','phone_use_violation') GROUP BY 1,2;",
]
for q in queries:
    print("---", q)
    subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", q],
        check=False,
    )
