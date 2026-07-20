#!/usr/bin/env python3
import json, os, urllib.request
API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")

def req(method, url, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token: h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())

login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
token = login["access_token"]
events = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=500", token=token)
if isinstance(events, dict):
    events = events.get("items", [])
counts = {}
for e in events:
    p = e.get("payload") or {}
    if isinstance(p, str):
        try: p = json.loads(p)
        except: p = {}
    if not p.get("demo"): continue
    et = p.get("event_type", "?")
    counts[et] = counts.get(et, 0) + 1
print("Demo event counts:")
for k, v in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")
counters = req("GET", f"{API}/api/v1/orgs/{ORG}/lines/counters", token=token)
print("\nLine counters:", counters)
print("MailHog:", req("GET", "http://127.0.0.1:8025/api/v2/messages?limit=1").get("total", 0))
