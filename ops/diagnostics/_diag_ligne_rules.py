#!/usr/bin/env python3
import json
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
LIGNE = "01ee632c-271c-4e66-ba98-3d1d7e430c09"

body = json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode()
tok = json.loads(urllib.request.urlopen(
    urllib.request.Request(API + "/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"})
).read())["access_token"]
h = {"Authorization": f"Bearer {tok}"}

rules = json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules", headers=h)).read())
print("=== Rules (enabled) ===")
for r in rules:
    if not r.get("is_enabled"):
        continue
    d = r.get("definition") or {}
    b = d.get("bindings") or {}
    cond = d.get("condition") or {}
    et = cond.get("value") if cond.get("field") in ("event_type", "event") else "?"
    print(f"  {r.get('name')}: cam={b.get('camera_id','?')[:8]} event={et}")

events = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/events?limit=100&include_incomplete=true", headers=h)).read())
ligne = [e for e in events if e.get("camera_id") == LIGNE]
by_type = {}
for e in ligne:
    et = e.get("event_type")
    snap = e.get("evidence_snapshot") or {}
    if isinstance(snap, str):
        snap = json.loads(snap) if snap else {}
    pkg = snap.get("package") or {}
    has_ev = bool((pkg.get("clip") or {}).get("url") or (pkg.get("images") or []))
    by_type.setdefault(et, {"total": 0, "with_ev": 0})
    by_type[et]["total"] += 1
    if has_ev:
        by_type[et]["with_ev"] += 1
print("\n=== Ligne Continue events ===")
for k, v in sorted(by_type.items()):
    print(f"  {k}: {v}")

alerts_raw = urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/alerts?limit=10&include_incomplete=true", headers=h)).read()
print("\n=== Alerts ===", alerts_raw[:300])
