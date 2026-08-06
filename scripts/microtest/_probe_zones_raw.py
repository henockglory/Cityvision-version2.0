#!/usr/bin/env python3
"""Read-only probe: raw zones payload for the feu camera + point-in-poly check."""
import json
import os
import urllib.request

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
CAM = "8ed20433-57d5-4999-a6ab-0bea028b23a3"
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
FRIGATE = "http://127.0.0.1:5000"


def req(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def point_in_poly(x, y, poly):
    pts = []
    for p in poly:
        if isinstance(p, dict):
            pts.append((float(p.get("x", 0)), float(p.get("y", 0))))
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append((float(p[0]), float(p[1])))
    if len(pts) < 3:
        return None
    inside = False
    j = len(pts) - 1
    for i, (xi, yi) in enumerate(pts):
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


tok = req("POST", f"{API}/api/v1/auth/login", {"email": EMAIL, "password": PASS})["access_token"]
zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token=tok)
if isinstance(zones, dict):
    zones = zones.get("zones") or zones.get("items") or []
print(f"zones total={len(zones)}")
obs_poly = None
for z in zones:
    if str(z.get("camera_id")) != CAM:
        continue
    keys = {k: z.get(k) for k in ("id", "name", "behavior", "zone_kind", "is_active") if k in z}
    bcfg = z.get("behavior_config")
    print("ZONE:", json.dumps(keys, default=str), "behavior_config keys:",
          list(bcfg.keys()) if isinstance(bcfg, dict) else bcfg)
    beh = str(z.get("behavior") or z.get("zone_kind") or "")
    if not beh and isinstance(bcfg, dict):
        beh = str(bcfg.get("behavior") or "")
    poly = z.get("polygon") or z.get("points") or []
    if isinstance(poly, str):
        try:
            poly = json.loads(poly)
        except json.JSONDecodeError:
            poly = []
    print(f"  resolved_behavior={beh!r} poly_points={len(poly)} sample={poly[:2]}")
    if beh == "red_light_observation":
        obs_poly = poly

print()
evs = req("GET", f"{FRIGATE}/api/events?camera=cv_{CAM}&limit=5")
for ev in evs:
    data = ev.get("data") or {}
    box = data.get("box")
    if not box or len(box) < 4:
        continue
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    inside = point_in_poly(cx, cy, obs_poly) if obs_poly else None
    print(f"event {str(ev.get('id'))[:22]} center=({cx:.3f},{cy:.3f}) in_obs={inside} zones={ev.get('zones')}")
