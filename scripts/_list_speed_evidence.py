#!/usr/bin/env python3
import json, subprocess, urllib.request
API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
body = json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode()
tok = json.loads(urllib.request.urlopen(urllib.request.Request(API + "/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"})).read())["access_token"]
h = {"Authorization": f"Bearer {tok}"}
events = json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/events?limit=50&include_incomplete=true&event_type=speeding", headers=h)).read())
for e in events:
    snap = e.get("evidence_snapshot") or {}
    if isinstance(snap, str): snap = json.loads(snap) if snap else {}
    pkg = snap.get("package") or {}
    clip = pkg.get("clip") or {}
    imgs = pkg.get("images") or []
    payload = e.get("payload") or {}
    if isinstance(payload, str): payload = json.loads(payload)
    print(e.get("occurred_at"), "speed=", payload.get("speed_kmh"), "clip=", bool(clip.get("url")), "imgs=", len(imgs))

alerts = json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/alerts?limit=50&include_incomplete=true", headers=h)).read()) or []
print("alerts", len(alerts))
