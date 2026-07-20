#!/usr/bin/env python3
import json
import os
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")

print("API", API)
print("EMAIL", repr(EMAIL))
print("PASS", repr(PASS[:4] + "..."))

for path in ("/health", "/api/v1/auth/login"):
    url = API + path
    if path.endswith("login"):
        body = json.dumps({"email": EMAIL, "password": PASS}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(path, "OK", r.status, r.read()[:80])
    except Exception as e:
        print(path, "FAIL", e)
