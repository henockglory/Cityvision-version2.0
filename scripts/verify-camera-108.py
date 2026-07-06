#!/usr/bin/env python3
import json
import urllib.error
import urllib.request

BASE = "http://localhost:8081/api/v1"
EMAIL = "glory.henock@hologram.cd"
PASSWORD = "TestMode2026!"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
CAM = "3f36b8bb-efaf-4bbe-afba-5ea94ed6556b"


def post(path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req).read())


def get(path, token):
    req = urllib.request.Request(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return urllib.request.urlopen(req).read()


login = post("/auth/login", {"email": EMAIL, "password": PASSWORD})
token = login["access_token"]
print("login ok")

try:
    preview = get(f"/orgs/{ORG}/cameras/{CAM}/preview", token)
    print("preview ok:", preview[:200])
except urllib.error.HTTPError as e:
    print("preview fail:", e.code, e.read()[:300])

streams = urllib.request.urlopen("http://localhost:1984/api/streams").read().decode()
print("go2rtc:", streams[:600])
