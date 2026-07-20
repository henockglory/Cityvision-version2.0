#!/usr/bin/env python3
"""Reset glory.henock demo password (WSL runtime)."""
import json
import subprocess
import sys
import urllib.request

import bcrypt

EMAIL = "glory.henock@hologram.cd"
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else "Hologram2026!"
API = "http://127.0.0.1:8081/api/v1/auth/login"

h = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
sql = f"UPDATE users SET password_hash = '{h}' WHERE email = '{EMAIL}';"
r = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
    capture_output=True,
    text=True,
)
print(r.stdout or r.stderr)
if r.returncode != 0:
    raise SystemExit(r.returncode)

body = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=15) as resp:
    print("login OK", resp.read()[:60])
