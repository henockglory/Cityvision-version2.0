#!/usr/bin/env python3
import json
import urllib.request

login = json.loads(
    urllib.request.urlopen(
        urllib.request.Request(
            "http://127.0.0.1:8081/api/v1/auth/login",
            data=json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    ).read()
)
token = login["access_token"]
org = "e312f375-7442-4089-8022-ed232abc09e8"
req = urllib.request.Request(
    f"http://127.0.0.1:8081/api/v1/orgs/{org}/events?limit=100",
    headers={"Authorization": f"Bearer {token}"},
)
rows = json.loads(urllib.request.urlopen(req).read())
print("count", len(rows))
for e in rows[:8]:
    p = e.get("payload") or {}
    if isinstance(p, str):
        p = json.loads(p)
    print(e.get("event_type"), "demo=", p.get("demo"), "payload_et=", p.get("event_type"))
