#!/usr/bin/env python3
import json, urllib.request
API = "http://127.0.0.1:8081/api/v1/auth/login"
creds = [
    ("glory.henock@hologram.cd", "Hologram2026!"),
    ("glory.henock@hologram.cd", "TestMode2026!"),
    ("admin@demo.local", "demo1234"),
    ("admin@citevision.local", "admin1234"),
]
for email, pw in creds:
    body = json.dumps({"email": email, "password": pw}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print("OK", email, pw[:4]+"...")
            break
    except Exception as e:
        print("FAIL", email, e)
