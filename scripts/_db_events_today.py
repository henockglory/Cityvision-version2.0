#!/usr/bin/env python3
import subprocess
sql = "SELECT event_type, occurred_at, left(id::text,8) FROM events WHERE occurred_at > '2026-07-01' ORDER BY occurred_at DESC LIMIT 30;"
out = subprocess.check_output(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-c", sql],
    text=True,
)
print(out or "(none)")
