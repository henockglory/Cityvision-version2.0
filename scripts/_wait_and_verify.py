#!/usr/bin/env python3
"""Attend que l'AI soit ready, resync, vérifie la zone et les premiers events."""
import json, urllib.request, time, subprocess

def get(url, headers=None, method="GET", data=None):
    req = urllib.request.Request(url, headers=headers or {}, method=method, data=data)
    try:
        return json.load(urllib.request.urlopen(req, timeout=10))
    except Exception as e:
        return {"error": str(e)}

ORG = "e312f375-7442-4089-8022-ed232abc09e8"

# 1. Attendre que l'AI engine soit healthy
print("Attente AI engine...")
for i in range(20):
    r = get("http://127.0.0.1:8001/health")
    if r.get("status") == "ok":
        print(f"  AI healthy après {i*3}s")
        break
    time.sleep(3)
else:
    print("  TIMEOUT - AI pas ready")
    exit(1)

# 2. Resync spatial pour pousser la nouvelle zone
print("Resync spatial...")
r2 = get("http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial",
         headers={"X-Internal-Key": "changeme_internal_service_key"},
         method="POST", data=b"")
print("  ", r2)

time.sleep(10)

# 3. Vérifier les caméras
print("Cameras AI:")
cams = get("http://127.0.0.1:8001/cameras")
for c in cams.get("cameras", []):
    print(f"  {c['camera_id']}  running={c.get('running')}  frames={c.get('frames_processed')}")

# 4. Vérifier la zone dans les logs AI
print("\nDerniers logs AI zone_speed:")
r3 = subprocess.run(
    ["bash", "-c", "tail -n 30 /home/gheno/citevision-v2/logs/ai-engine.log | grep zone_speed | tail -5"],
    capture_output=True, text=True)
print(r3.stdout.strip() or "(rien)")

# 5. Vérifier s'il y a des nouveaux events en DB
def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

print("\nDerniers events speeding (30 dernières min):")
rows = psql("""
  SELECT created_at, payload->>'speed_kmh' as spd, camera_id
  FROM events WHERE type='speeding' AND created_at > NOW() - INTERVAL '30 minutes'
  ORDER BY created_at DESC LIMIT 5;
""")
print(rows or "(aucun)")
