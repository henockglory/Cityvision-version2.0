#!/usr/bin/env python3
import subprocess
SQL = "SELECT created_at::text, metadata->>'speed_kmh' FROM alerts WHERE metadata->>'camera_id'='37c7d7fa-12dc-450c-8c4b-ab63ed43a819' ORDER BY created_at DESC LIMIT 5;"
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", SQL]
print(subprocess.run(cmd, capture_output=True, text=True).stdout)
