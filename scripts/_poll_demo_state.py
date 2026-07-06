#!/usr/bin/env python3
import json, os, urllib.request
API = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"

def req(method, url, token=None, body=None):
    h = {"Content-Type": "application/json"}
    if token: h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())

tok = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})["access_token"]
events = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=30", tok)
if isinstance(events, dict): events = events.get("items", [])
alerts = req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=20&include_incomplete=true", tok)
if isinstance(alerts, dict): alerts = alerts.get("items", [])
print("=== recent events ===")
for e in events[:15]:
    et = e.get("event_type") or e.get("type")
    snap = e.get("evidence_snapshot") or e.get("evidenceSnapshot") or {}
    pkg = snap.get("package") if isinstance(snap, dict) else None
    slots = 0
    if isinstance(pkg, dict):
        if pkg.get("clip"): slots += 1
        slots += len(pkg.get("images") or [])
    print(f"  {et} cam={str(e.get('camera_id',''))[:8]} pkg_slots={slots}")
print("=== recent alerts ===")
for a in alerts[:10]:
    snap = a.get("evidence_snapshot") or a.get("evidenceSnapshot") or {}
    pkg = snap.get("package") if isinstance(snap, dict) else None
    slots = 0
    if isinstance(pkg, dict):
        if pkg.get("clip"): slots += 1
        slots += len(pkg.get("images") or [])
    print(f"  {a.get('title') or a.get('message','?')} rule={str(a.get('rule_id',''))[:8]} pkg_slots={slots}")
