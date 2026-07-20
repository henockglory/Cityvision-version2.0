#!/usr/bin/env python3
"""Try login with passwords from env/docs."""
import json
import os
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8081/api/v1/auth/login"
for p in (Path.home() / "citevision-v2" / ".env",):
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

email = os.environ.get("DEMO_EMAIL", os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd"))
passwords = [
    os.environ.get("DEMO_PASS", ""),
    os.environ.get("ADMIN_PASSWORD", ""),
    "Hologram2026!",
    "TestMode2026!",
    "demo1234",
]
seen = set()
for pw in passwords:
    if not pw or pw in seen:
        continue
    seen.add(pw)
    body = json.dumps({"email": email, "password": pw}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print("OK", email, "password=", pw[:4] + "…")
            break
    except Exception as e:
        print("FAIL", pw[:4] + "…", e)
