#!/usr/bin/env python3
"""Vérifie que l'IA détecte bien des véhicules et que la zone_speed est active."""
import json, urllib.request, time

def curl(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try: return json.load(urllib.request.urlopen(req, timeout=5))
    except Exception as e: return {"_error": str(e)}

CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"

# 1. Camera detailed status
cams = curl("http://127.0.0.1:8001/cameras")
for c in (cams.get("cameras") or []):
    print(f"[Camera] running={c.get('running')}  fps={c.get('fps')}  frames={c.get('frames_processed')}")
    print(f"         detections_total={c.get('detections_total')}  last_detection={c.get('last_detection_at')}")

# 2. Zone spatial dans l'IA (vérifie les zones chargées)
sp = curl(f"http://127.0.0.1:8001/cameras/{CAM}/spatial")
print(f"[Spatial] zone_count={sp.get('zone_count')}  zone_speed_active={sp.get('zone_speed_active')}")
print(f"          behaviors={sp.get('behaviors')}")

# 3. Mesure delta frames sur 15s
f1 = (curl("http://127.0.0.1:8001/cameras")
      .get("cameras", [{}])[0].get("frames_processed", 0))
time.sleep(15)
cams2 = curl("http://127.0.0.1:8001/cameras")
c2 = (cams2.get("cameras") or [{}])[0]
f2 = c2.get("frames_processed", 0)
d2 = c2.get("detections_total", 0)
print(f"[Delta 15s] frames: {f1} → {f2} (+{f2-f1})  dets_total={d2}")

# 4. Log snippet - cherche speed/zone/detection dans les logs
import subprocess
r = subprocess.run(
    ["wsl", "grep", "-E", "speed_kmh|zone_speed|ZoneSpeed|enter.*zone|exit.*zone|SPEED|speeding|track.*inside|no track",
     "/mnt/c/Users/gheno/citevision/logs/ai-engine.log"],
    capture_output=True, text=True
)
lines = r.stdout.strip().splitlines()
print(f"[Logs speed/zone] {len(lines)} lignes")
for l in lines[-10:]:
    print(" ", l[:120])
