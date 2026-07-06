#!/usr/bin/env python3
import json
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
LIGNE = "01ee632c-271c-4e66-ba98-3d1d7e430c09"

body = json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode()
req = urllib.request.Request(API + "/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"})
tok = json.loads(urllib.request.urlopen(req).read())["access_token"]
h = {"Authorization": f"Bearer {tok}"}

events = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/events?limit=200&include_incomplete=true", headers=h)).read())
rules = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/rules", headers=h)).read())

print(f"events total={len(events)}")
enabled = [r for r in rules if r.get("is_enabled") and (r.get("definition", {}).get("bindings") or {}).get("origin") == "user"]
rule_types = set()
for r in enabled:
    cond = (r.get("definition") or {}).get("condition") or {}
    if cond.get("field") in ("event_type", "event"):
        rule_types.add(str(cond.get("value")))
    for c in (cond.get("children") or []):
        if c.get("field") in ("event_type", "event"):
            rule_types.add(str(c.get("value")))
print(f"enabled user rules={len(enabled)} types={rule_types}")

ligne = [e for e in events if e.get("camera_id") == LIGNE]
print(f"ligne events={len(ligne)}")
by_type = {}
for e in ligne:
    et = e.get("event_type")
    by_type[et] = by_type.get(et, 0) + 1
print("by_type", by_type)

for et in ["speeding", "line_cross", "vehicle_stopped"]:
    matches = [e for e in ligne if e.get("event_type") == et]
    if not matches:
        continue
    e = matches[0]
    snap = e.get("evidence_snapshot") or {}
    if isinstance(snap, str):
        snap = json.loads(snap) if snap else {}
    pkg = (snap.get("package") or {}) if isinstance(snap, dict) else {}
    clip = pkg.get("clip") or {}
    imgs = pkg.get("images") or []
    payload = e.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    ppkg = payload.get("package") or {}
    print(f"\n{et} sample:")
    print(f"  snap clip={bool(clip.get('url') or clip.get('asset_id'))} images={len(imgs)}")
    print(f"  payload package={bool(ppkg)}")

alerts_raw = urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/alerts?limit=20&include_incomplete=true&status=open", headers=h)).read()
print("\nalerts raw:", alerts_raw[:200])
