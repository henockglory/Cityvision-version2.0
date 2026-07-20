#!/usr/bin/env python3
import subprocess

queries = [
    "SELECT camera_id, event_type, count(1) FROM events WHERE event_type IN ('phone_driving','phone_use_violation') GROUP BY 1,2;",
    "SELECT camera_id, event_type, count(1) FROM events WHERE event_type IN ('seatbelt_violation') GROUP BY 1,2;",
    "SELECT id, name FROM cameras WHERE org_id='e312f375-7442-4089-8022-ed232abc09e8';",
]
for q in queries:
    print("---", q)
    subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", q],
        check=False,
    )
