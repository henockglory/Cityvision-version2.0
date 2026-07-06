#!/usr/bin/env python3
import subprocess

queries = [
    "SELECT event_type, count(1) FROM events WHERE event_type IN ('traffic_light_state','red_light_violation','speeding') GROUP BY 1;",
    "SELECT event_type, occurred_at FROM events WHERE event_type='traffic_light_state' ORDER BY occurred_at DESC LIMIT 5;",
    "SELECT event_type, count(1) FROM events WHERE occurred_at > now() - interval '5 minutes' GROUP BY 1 ORDER BY 2 DESC LIMIT 10;",
]
for q in queries:
    print("---", q[:60], "...")
    subprocess.run(
        [
            "docker",
            "exec",
            "citevision-v2-postgres",
            "psql",
            "-U",
            "citevision",
            "-d",
            "citevision",
            "-c",
            q,
        ],
        check=False,
    )
