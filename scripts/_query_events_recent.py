#!/usr/bin/env python3
import subprocess

q = """
SELECT event_type, count(1)
FROM events
WHERE event_type IN ('traffic_light_state','red_light_violation','speeding')
  AND occurred_at > now() - interval '15 minutes'
GROUP BY 1 ORDER BY 1;
"""
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
        q.strip(),
    ],
    check=False,
)
