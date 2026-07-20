#!/usr/bin/env python3
"""Run SQL via docker postgres."""
import subprocess
import sys

sql = sys.argv[1] if len(sys.argv) > 1 else "SELECT email FROM users LIMIT 5;"
cmd = [
    "docker", "exec", "citevision-v2-postgres",
    "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
]
r = subprocess.run(cmd, capture_output=True, text=True)
print(r.stdout)
if r.stderr:
    print(r.stderr, file=sys.stderr)
sys.exit(r.returncode)
