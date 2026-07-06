#!/usr/bin/env python3
"""Diagnose red-light and speed pipelines."""
import json
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"

def req(method, url, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())

login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
token = login["access_token"]

# Event types relevant to red light / speed
events = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=500", token=token)
if isinstance(events, dict):
    events = events.get("items", [])

watch = (
    "traffic_light_state",
    "red_light_violation",
    "speeding",
    "vehicle_corridor",
    "line_cross",
)
counts = {w: 0 for w in watch}
speed_samples = []
for e in events:
    p = e.get("payload") or {}
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            p = {}
    et = p.get("event_type") or e.get("event_type", "")
    if et not in watch:
        continue
    if not p.get("demo"):
        continue
    counts[et] = counts.get(et, 0) + 1
    if et == "vehicle_corridor" and p.get("speed_kmh"):
        speed_samples.append(float(p["speed_kmh"]))
    if et == "traffic_light_state":
        meta = p.get("metadata") or {}
        print(f"  traffic_light_state: {meta.get('state')}")

print("\nAll org events (any demo flag) for pipeline types:")
for et in watch:
    n = sum(1 for e in events if (_payload(e).get("event_type") or e.get("event_type")) == et)
    print(f"  {et}: {n}")
if speed_samples:
    print(f"  vehicle_corridor speed_kmh samples: min={min(speed_samples):.1f} max={max(speed_samples):.1f} n={len(speed_samples)}")

# Zones on feux + ligne continue cameras
zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token=token)
if isinstance(zones, dict):
    zones = zones.get("items", zones)
for z in zones or []:
    name = z.get("name", "")
    if name not in ("Zone_des_feux", "Zone_Observation", "Zone_distance_parcourue"):
        continue
    cam = z.get("camera_id", "")
    bc = z.get("behavior_config")
    if isinstance(bc, str):
        bc = json.loads(bc) if bc.startswith("{") else bc
    print(f"\nZone {name} cam={cam[:8] if cam else '?'}...")
    print(f"  behavior_config: {json.dumps(bc, ensure_ascii=False)[:200]}")

# AI cameras
with urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=10) as r:
    cams = json.loads(r.read()).get("cameras", [])
print("\nAI ingest:")
for c in cams:
    cid = c["camera_id"]
    if cid.startswith("726ff8a1") or cid.startswith("01ee632c"):
        print(f"  {cid[:8]} fps={c.get('fps')} frames={c.get('frames_processed')} err={c.get('last_error')}")
