#!/usr/bin/env python3
"""Quick status during E2E validation."""
import json
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"


def req(method, url, token=None, body=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
token = login["access_token"]

with urllib.request.urlopen("http://127.0.0.1:8010/health") as resp:
    re = json.loads(resp.read())
print("rules-engine:", re)

rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", token)
enabled = [r["name"] for r in rules if r.get("is_enabled")]
print("enabled rules:", enabled)

for et in (
    "red_light_violation",
    "traffic_light_state",
    "speeding",
    "line_cross",
    "phone_use_violation",
    "seatbelt_violation",
):
    rows = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=20&event_type={et}", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    demo = 0
    for e in rows:
        p = e.get("payload") or {}
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except json.JSONDecodeError:
                p = {}
        if p.get("demo") is True:
            demo += 1
    print(f"{et}: total_recent={len(rows)} demo_tagged={demo}")

with urllib.request.urlopen(f"{API}/api/v1/orgs/{ORG}/alerts?limit=5") as resp:
    pass

alerts = req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=50", token)
if not isinstance(alerts, list):
    alerts = alerts.get("items", [])
print("alerts total:", len(alerts))

with urllib.request.urlopen("http://127.0.0.1:8001/cameras/726ff8a1-8442-4bdb-96ad-ec40a2fbb424/spatial") as resp:
    sp = json.loads(resp.read())
print("feux spatial:", {k: sp.get(k) for k in ("traffic_light_active", "traffic_light_state", "behaviors")})
