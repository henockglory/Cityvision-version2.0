#!/usr/bin/env python3
"""Diagnose feu bbox vs observation zone alignment."""
import json
import os
import subprocess
import urllib.parse
import urllib.request

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
CAM = "8ed20433-57d5-4999-a6ab-0bea028b23a3"
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
FRIGATE = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")


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
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1):
            inside = not inside
    return inside


tok = req("POST", f"{API}/api/v1/auth/login", {"email": EMAIL, "password": PASS})["access_token"]
zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token=tok)
obs = None
light = None
for z in zones:
    if str(z.get("camera_id")) != CAM:
        continue
    beh = str(z.get("behavior") or "")
    if beh == "red_light_observation":
        obs = z
    if beh == "traffic_light_color":
        light = z
print("obs zone", obs.get("name") if obs else None, "id", (obs or {}).get("id"))
print("light zone", light.get("name") if light else None)
obs_poly = (obs or {}).get("polygon") or []
if isinstance(obs_poly, str):
    obs_poly = json.loads(obs_poly)
print("obs poly points", len(obs_poly))

qs = urllib.parse.urlencode({"camera": f"cv_{CAM}", "limit": 10})
events = json.loads(urllib.request.urlopen(f"{FRIGATE}/api/events?{qs}", timeout=10).read())
cars = [e for e in events if str(e.get("label")).lower() == "car" and e.get("end_time")][:5]
for ev in cars:
    data = ev.get("data") or {}
    box = data.get("box")
    if not box or len(box) < 4:
        continue
    x, y, w, h = box[0], box[1], box[2], box[3]
    cx, cy = x + w / 2, y + h / 2
    inside = point_in_poly(cx, cy, obs_poly) if obs_poly else None
    print(f"event {str(ev.get('id'))[:20]} box={box[:4]} center=({cx:.3f},{cy:.3f}) in_obs={inside}")
