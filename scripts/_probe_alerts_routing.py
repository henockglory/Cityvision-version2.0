#!/usr/bin/env python3
import json, urllib.request, os
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")

def req(method, url, token=None, body=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read().decode() or "{}")

login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
token = login["access_token"]
org = req("GET", f"{API}/api/v1/auth/me", token)["org_id"]
for path in [f"/api/v1/orgs/{org}/alerts?limit=3", f"/api/v1/orgs/{org}/routing-rules"]:
    try:
        data = req("GET", f"{API}{path}", token)
        print(path, type(data).__name__, json.dumps(data, ensure_ascii=False)[:600])
    except Exception as e:
        print(path, "ERR", e)
