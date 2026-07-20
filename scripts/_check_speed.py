#!/usr/bin/env python3
"""Vérifie vitesse pipeline : fps réel, circuit-breaker OCR, détections zone."""
import json, urllib.request, time

def curl(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try: return json.load(urllib.request.urlopen(req, timeout=5))
    except Exception as e: return {"_error": str(e)}

# Mesure delta frames sur 10s
cams1 = curl("http://127.0.0.1:8001/cameras")
c1 = (cams1.get("cameras") or [{}])[0]
f1 = c1.get("frames_processed", 0)
print(f"t=0  frames={f1}  running={c1.get('running')}  fps_config={c1.get('fps')}")

time.sleep(10)

cams2 = curl("http://127.0.0.1:8001/cameras")
c2 = (cams2.get("cameras") or [{}])[0]
f2 = c2.get("frames_processed", 0)
delta = f2 - f1
print(f"t=10 frames={f2}  delta={delta}  fps_réel≈{delta/10:.1f}")

# Circuit-breaker dans les logs
import subprocess
r = subprocess.run(
    ["grep", "-c", "circuit-breaker", "/home/gheno/citevision-v2/logs/ai-engine.log"],
    capture_output=True, text=True
)
print(f"circuit-breaker logs: {r.stdout.strip()}")

r2 = subprocess.run(
    ["grep", "circuit-breaker", "/home/gheno/citevision-v2/logs/ai-engine.log"],
    capture_output=True, text=True
)
for l in r2.stdout.strip().splitlines()[:3]:
    print(" ", l[:120])

# Events récents
IKEY = {"X-Internal-Key": "changeme_internal_service_key"}
evts = curl("http://127.0.0.1:8081/api/v1/events?limit=3&sort=desc", headers=IKEY)
items = evts if isinstance(evts, list) else (evts.get("items") or evts.get("events") or [])
print(f"Events récents: {len(items)}")
for e in items[:3]:
    ts = e.get("timestamp") or e.get("created_at") or "?"
    print(f"  {e.get('type','?'):20}  ts={ts[:19]}")
