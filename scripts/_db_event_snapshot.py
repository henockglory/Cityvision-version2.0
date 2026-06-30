#!/usr/bin/env python3
import subprocess

queries = [
    "SELECT event_type, count(1) FROM events GROUP BY 1 ORDER BY 2 DESC LIMIT 15;",
    "SELECT event_type, count(1) FROM events WHERE payload->>'demo' = 'true' GROUP BY 1 ORDER BY 2 DESC LIMIT 10;",
    "SELECT event_type, occurred_at FROM events WHERE event_type IN ('traffic_light_state','red_light_violation','speeding','line_cross') ORDER BY occurred_at DESC LIMIT 8;",
]
for q in queries:
    print("---")
    subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", q],
        check=False,
    )
