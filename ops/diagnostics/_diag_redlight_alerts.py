#!/usr/bin/env python3
import json, os, urllib.request
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")

def req(method, url, token=None, body=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode() or "{}")

tok = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})["access_token"]
rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
for r in rules:
    if "Feu rouge" in r.get("name", ""):
        print("RULE", r["name"], "enabled", r.get("is_enabled"))
        print(json.dumps(r.get("definition"), indent=2)[:1200])
for et in ["red_light_violation", "speeding"]:
    rows = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=5&event_type={et}", tok)
    print(f"\n=== {et} ({len(rows)}) ===")
    for e in rows[:3]:
        p = e.get("payload") or {}
        if isinstance(p, str):
            p = json.loads(p)
        print(" id", str(e.get("id", ""))[:8], "cam", str(e.get("camera_id", ""))[:8])
        print(" demo", p.get("demo"), "event_type", p.get("event_type"))
alerts = req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=10", tok)
print(f"\n=== alerts ({len(alerts)}) ===")
for a in alerts[:5]:
    m = a.get("metadata") or {}
    if isinstance(m, str):
        m = json.loads(m)
    print(a.get("title"), m.get("event_type"), m.get("demo"))
