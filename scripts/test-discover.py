#!/usr/bin/env python3
import json
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8081/api/v1"
login = json.dumps({"email": "glory.henock@hologram.cd", "password": "TestMode2026!"})
req = urllib.request.Request(
    f"{BASE}/auth/login",
    data=login.encode(),
    headers={"Content-Type": "application/json"},
)
token = json.load(urllib.request.urlopen(req))["access_token"]
org = "e312f375-7442-4089-8022-ed232abc09e8"
headers = {"Authorization": f"Bearer {token}", "X-Org-ID": org}
cidr = "192.168.1.0/24"
url = f"{BASE}/orgs/{org}/cameras/discover?cidr={cidr.replace('/', '%2F')}"
print("GET", url)
start = time.time()
try:
    resp = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)
    data = json.load(resp)
    print("status:", resp.status, "devices:", len(data), "elapsed:", round(time.time() - start, 1), "s")
    for d in data[:5]:
        print(" ", d)
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read()[:500], "elapsed:", round(time.time() - start, 1))
except Exception as e:
    print("ERR", e, "elapsed:", round(time.time() - start, 1))
