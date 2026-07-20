#!/usr/bin/env python3
import os
from pathlib import Path

env = {}
for p in (Path.home() / "citevision-v2" / ".env",):
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")

import subprocess
host = env.get("POSTGRES_HOST", "localhost")
port = env.get("POSTGRES_PORT", "5433")
user = env.get("POSTGRES_USER", "citevision")
db = env.get("POSTGRES_DB", "citevision")
pw = env.get("POSTGRES_PASSWORD", "citevision")
env_vars = {**os.environ, "PGPASSWORD": pw}
cmd = ["psql", "-h", host, "-p", port, "-U", user, "-d", db, "-t", "-c", "SELECT email FROM users LIMIT 5;"]
print(subprocess.run(cmd, env=env_vars, capture_output=True, text=True).stdout)
