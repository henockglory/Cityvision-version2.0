#!/usr/bin/env python3
import json
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
cams = json.load(
    urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/orgs/{org}/cameras", headers=headers)
    )
)
print("cameras:", len(cams))
if not cams:
    raise SystemExit("no cameras to test")
cam_id = cams[-1]["id"]
print("deleting", cam_id)
del_req = urllib.request.Request(
    f"{BASE}/orgs/{org}/cameras/{cam_id}",
    method="DELETE",
    headers=headers,
)
try:
    resp = urllib.request.urlopen(del_req)
    body = resp.read().decode() or "{}"
    print("delete status:", resp.status)
    print("delete body:", body)
    data = json.loads(body)
    if not data.get("deleted"):
        raise SystemExit("expected deleted=true in response")
except urllib.error.HTTPError as e:
    print("delete failed:", e.code, e.read()[:300])
