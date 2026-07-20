#!/usr/bin/env python3
"""Quick snapshot of demo events and health."""
import json
import os
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")


def get(url, token=None, method="GET", body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


ai = get("http://127.0.0.1:8001/health")
print("AI:", {k: ai[k] for k in ("yolo_loaded", "driver_phone_model_loaded", "seatbelt_model_loaded")})
re = get("http://127.0.0.1:8010/health")
print("Rules:", re)
login = get(f"{API}/api/v1/auth/login", method="POST", body={"email": EMAIL, "password": PASS})
token = login["access_token"]
events = get(f"{API}/api/v1/orgs/{ORG}/events?limit=50", token=token)
if isinstance(events, dict):
    events = events.get("items", [])
types = {}
for e in events:
    p = e.get("payload") or {}
    if isinstance(p, str):
        p = json.loads(p) if p.startswith("{") else {}
    et = p.get("event_type") or e.get("event_type", "?")
    demo = p.get("demo")
    key = f"{et}{' (demo)' if demo else ''}"
    types[key] = types.get(key, 0) + 1
print(f"Recent events ({len(events)}):")
for k, v in sorted(types.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")
alerts = get(f"{API}/api/v1/orgs/{ORG}/alerts?limit=10", token=token)
if isinstance(alerts, dict):
    alerts = alerts.get("items", [])
print(f"Recent alerts: {len(alerts)}")
try:
    mh = get("http://127.0.0.1:8025/api/v2/messages?limit=1")
    print(f"MailHog messages: {mh.get('total', 0)}")
except Exception as ex:
    print(f"MailHog: {ex}")
