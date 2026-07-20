#!/usr/bin/env python3
"""Why demo UI shows zero detections."""
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

def get(path):
    return json.loads(urllib.request.urlopen(urllib.request.Request(API + path, headers=h)).read())

ds = get(f"/api/v1/orgs/{ORG}/demo/settings")
rules = get(f"/api/v1/orgs/{ORG}/rules")
events = get(f"/api/v1/orgs/{ORG}/events?limit=200&include_incomplete=true")
cameras = get(f"/api/v1/orgs/{ORG}/cameras")

print("=== Demo source ===")
print("source_mode:", ds.get("source_mode"))
print("active_video_id:", ds.get("active_video_id"))
print("active_camera_id:", ds.get("active_camera_id"))

enabled = [r for r in rules if r.get("is_enabled") and (r.get("definition", {}).get("bindings") or {}).get("origin") == "user"]
rule_types = set()
for r in enabled:
    cond = (r.get("definition") or {}).get("condition") or {}
    if cond.get("field") in ("event_type", "event"):
        rule_types.add(str(cond.get("value")))
    for c in (cond.get("children") or []):
        if c.get("field") in ("event_type", "event"):
            rule_types.add(str(c.get("value")))
print("\n=== Enabled rule event types ===", rule_types)

ligne = [e for e in events if e.get("camera_id") == LIGNE]
print(f"\n=== Ligne Continue: {len(ligne)} events in DB ===")
by_type = {}
for e in ligne:
    et = e.get("event_type")
    by_type.setdefault(et, {"total": 0, "with_ev": 0, "matches_rule": 0})
    by_type[et]["total"] += 1
    snap = e.get("evidence_snapshot") or {}
    if isinstance(snap, str):
        snap = json.loads(snap) if snap else {}
    pkg = (snap.get("package") or {}) if isinstance(snap, dict) else {}
    clip = pkg.get("clip") or {}
    imgs = pkg.get("images") or []
    has_ev = bool(clip.get("url") or clip.get("asset_id") or imgs)
    if has_ev:
        by_type[et]["with_ev"] += 1
    if et in rule_types:
        by_type[et]["matches_rule"] += 1

for et, stats in sorted(by_type.items()):
    ui_visible = stats["matches_rule"] if stats["matches_rule"] and stats["with_ev"] else 0
    print(f"  {et}: total={stats['total']} matches_rule={stats['matches_rule']} with_evidence={stats['with_ev']} -> UI would show ~{ui_visible}")

print("\n=== Frontend filter logic ===")
print("Events shown only if: camera in scope AND event_type in active rules AND has evidence (clip/images)")

# AI spatial
try:
    spatial = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"http://127.0.0.1:8001/cameras/{LIGNE}/spatial", timeout=8)
    ).read())
    print("\n=== AI spatial (Ligne) ===")
    print(json.dumps(spatial, indent=2))
except Exception as exc:
    print("\n=== AI spatial FAILED ===", exc)

try:
    cams = json.loads(urllib.request.urlopen(
        urllib.request.Request("http://127.0.0.1:8001/cameras", timeout=8)
    ).read())
    print("\n=== AI ingest ===")
    for c in cams.get("cameras", []):
        print(f"  {c.get('camera_id')}: running={c.get('running')} frames={c.get('frames_processed')}")
except Exception as exc:
    print("\n=== AI cameras FAILED ===", exc)
