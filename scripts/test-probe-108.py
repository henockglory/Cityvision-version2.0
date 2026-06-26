#!/usr/bin/env python3
import json
import urllib.request

BASE = "http://localhost:8081/api/v1"
login = json.dumps({"email": "glory.henock@hologram.cd", "password": "TestMode2026!"})
token = json.load(urllib.request.urlopen(urllib.request.Request(
    f"{BASE}/auth/login", data=login.encode(), headers={"Content-Type": "application/json"},
)))["access_token"]
org = "e312f375-7442-4089-8022-ed232abc09e8"
headers = {"Authorization": f"Bearer {token}", "X-Org-ID": org, "Content-Type": "application/json"}

# probe with auto vendor - password must be set by user; try empty and common
import os
password = os.environ.get("CAM_PASS", "")
body = json.dumps({"host": "192.168.1.108", "port": 554, "username": "admin", "password": password, "vendor": "auto"}).encode()
req = urllib.request.Request(f"{BASE}/orgs/{org}/cameras/probe", data=body, headers=headers, method="POST")
resp = urllib.request.urlopen(req, timeout=60)
data = json.load(resp)
print("best:", json.dumps(data.get("best"), indent=2))
print("ffprobe:", json.dumps(data.get("ffprobe"), indent=2))
for c in data.get("candidates", []):
    if c.get("ok"):
        print("ok candidate:", c.get("vendor"), c.get("rtsp_path"), c.get("url"))
