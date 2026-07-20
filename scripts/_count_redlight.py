#!/usr/bin/env python3
import json, os, urllib.request
API = "http://127.0.0.1:8081"
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
ORG = "e312f375-7442-4089-8022-ed232abc09e8"

def req(url, tok=None, body=None):
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=h, method="POST" if body else "GET")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())

tok = req(f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})["access_token"]
rows = req(f"{API}/api/v1/orgs/{ORG}/events?limit=100&event_type=red_light_violation", tok)
demo = 0
for e in rows or []:
    p = e.get("payload") or {}
    if isinstance(p, str):
        p = json.loads(p)
    if p.get("demo") is True:
        demo += 1
print("red_light_violation total", len(rows or []), "demo", demo)
alerts = req(f"{API}/api/v1/orgs/{ORG}/alerts?limit=50", tok)
def meta_demo(a):
    m = a.get("metadata") or {}
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except json.JSONDecodeError:
            m = {}
    return m.get("demo") is True

demo_alerts = sum(1 for a in (alerts or []) if meta_demo(a))
print("alerts total", len(alerts or []), "demo", demo_alerts)
