#!/usr/bin/env python3
import json
import urllib.error
import urllib.request
from pathlib import Path

env = {}
p = Path.home() / "citevision-v2" / ".env"
if p.exists():
    for line in p.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')

candidates = [
    env.get("ADMIN_PASSWORD", ""),
    env.get("CV_ADMIN_PASSWORD", ""),
    env.get("DEFAULT_ADMIN_PASSWORD", ""),
    "Hologram2026!",
    "Henockglory@03",
]
api = "http://127.0.0.1:8081/api/v1/auth/login"
for pwd in candidates:
    if not pwd:
        continue
    body = json.dumps({"email": "glory.henock@hologram.cd", "password": pwd}).encode()
    req = urllib.request.Request(api, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            print("OK", "has_token", bool(data.get("access_token")))
            break
    except urllib.error.HTTPError as e:
        print("FAIL", e.code)
else:
    print("NO_LOGIN")
