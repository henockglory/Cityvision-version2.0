#!/usr/bin/env python3
"""Check recent events for f691ef55 cabin camera in DB."""
import urllib.request, json, sys, os

API = "http://localhost:8081"
EMAIL = "glory.henock@hologram.cd"
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
CABIN_CAM = "f691ef55-6791-495b-a35e-be215e7ac109"

data = json.dumps({"email": EMAIL, "password": PASS}).encode()
req = urllib.request.Request(f"{API}/api/v1/auth/login", data=data,
                              headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=10) as r:
    auth = json.loads(r.read())
token = auth.get("access_token") or auth.get("token")
h = {"Authorization": f"Bearer {token}"}

# Query last 20 events for cabin camera
req2 = urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/events?limit=20&camera_id={CABIN_CAM}",
    headers=h
)
try:
    with urllib.request.urlopen(req2, timeout=10) as r:
        events = json.loads(r.read())
except Exception as e:
    print(f"camera_id filter: {e}")
    # try without camera filter
    req3 = urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/events?limit=20", headers=h)
    with urllib.request.urlopen(req3, timeout=10) as r:
        events = json.loads(r.read())

rows = events if isinstance(events, list) else events.get("items", [])
print(f"Events found: {len(rows)}")
for e in rows[:10]:
    p = e.get("payload") or {}
    if isinstance(p, str):
        try: p = json.loads(p)
        except: pass
    print(f"  cam={str(e.get('camera_id',''))[:8]} type={e.get('event_type')} demo={p.get('demo')} id={str(e.get('id',''))[:8]}")
