#!/usr/bin/env python3
"""
Repositionne la zone de vitesse là où les véhicules sont réellement visibles.
D'après les logs, les véhicules sont à y=0.08-0.27 (tiers supérieur de l'écran).
Bande fine : ENTRÉE à y=0.24, SORTIE à y=0.09.
x couvre x=0.25-0.75 (zone de passage).
"""
import json, subprocess, urllib.request, time

ORG  = "e312f375-7442-4089-8022-ed232abc09e8"
ZONE = "Zone_distance_parcourue"

# ── Bande fine dans la VRAIE zone de passage des véhicules ─────────────────
# Véhicules : bas → haut (y décroissant dans les données).
# ENTRY = y=0.24 (bas de la bande), EXIT = y=0.09 (haut de la bande).
# Hauteur = 0.15 unités → échelle ≈ 53 m/unité avec 8 m calibrés.
X_L  = 0.25
X_R  = 0.75
Y_TOP = 0.09   # ligne EXIT (sortie haut)
Y_BOT = 0.24   # ligne ENTRY (entrée bas)

polygon = [
    {"x": X_L, "y": Y_TOP},                              # P0 top-left
    {"x": X_R, "y": Y_TOP, "distance_to_next_m": 8.0},  # P1 top-right  → P2 = côté droit 8 m
    {"x": X_R, "y": Y_BOT},                              # P2 bottom-right
    {"x": X_L, "y": Y_BOT, "distance_to_next_m": 8.0},  # P3 bottom-left → P0 = côté gauche 8 m
]

behavior_config = {
    "behavior": "speed_measurement",
    "config": {
        "distance_m": 8.0,
        "edge_distances_m": [None, 8.0, None, 8.0],
        "speed_limit_kmh": 1.0,
        "cooldown_sec": 2.0,
        "spatial_dedup_sec": 2.0,
        "class_filter": "any",
    },
}

poly_json = json.dumps(polygon).replace("'", "''")
beh_json  = json.dumps(behavior_config).replace("'", "''")

sql = f"""
UPDATE zones
SET polygon         = '{poly_json}'::jsonb,
    behavior_config = '{beh_json}'::jsonb,
    zone_kind       = 'speed_measurement',
    updated_at      = NOW()
WHERE org_id = '{ORG}'::uuid AND name = '{ZONE}';
"""

r = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres",
     "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
    capture_output=True, text=True)
print("DB update:", r.stdout.strip())
if r.stderr.strip():
    print("ERR:", r.stderr.strip())

# ── Forcer le rechargement côté backend ─────────────────────────────────────
print("\nResync backend...")
req = urllib.request.Request(
    "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial",
    data=b"", method="POST",
    headers={"X-Internal-Key": "changeme_internal_service_key"})
resp = urllib.request.urlopen(req, timeout=10)
print("Backend resync:", resp.read().decode())

# ── Forcer le rechargement côté AI engine ────────────────────────────────────
print("\nRestart camera ingest on AI engine...")
CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
# Arrêter l'ingest de la caméra
stop_req = urllib.request.Request(
    f"http://127.0.0.1:8001/cameras/{CAM}/stop",
    data=b"", method="POST")
try:
    r2 = urllib.request.urlopen(stop_req, timeout=5)
    print("Camera stop:", r2.read().decode())
except Exception as e:
    print("Camera stop (ignoré):", e)

time.sleep(3)

# Redémarrer l'ingest de la caméra
start_req = urllib.request.Request(
    f"http://127.0.0.1:8001/cameras/{CAM}/start",
    data=b"", method="POST")
try:
    r3 = urllib.request.urlopen(start_req, timeout=5)
    print("Camera start:", r3.read().decode())
except Exception as e:
    print("Camera start (ignoré):", e)

time.sleep(5)

# Vérifier que le rechargement a eu lieu
print("\nVérification de la nouvelle zone dans l'AI engine...")
req2 = urllib.request.Request(
    f"http://127.0.0.1:8081/api/v1/internal/ingest/orgs/{ORG}/cameras/{CAM}/spatial-config",
    headers={"X-Internal-Key": "changeme_internal_service_key"})
d = json.load(urllib.request.urlopen(req2, timeout=10))
for z in d.get("zones", []):
    if z.get("zone_kind") == "speed_measurement":
        poly = z["polygon"]
        ys = [p["y"] for p in poly]
        print(f"Zone {z['zone_id']}: poly_y=[{min(ys):.2f}-{max(ys):.2f}]  ✓" if abs(min(ys) - Y_TOP) < 0.01 else "  ← ANCIENNE ZONE, pas encore rechargée")
        for i, p in enumerate(poly):
            print(f"  P{i} ({p['x']:.3f}, {p['y']:.3f})  dist={p.get('distance_to_next_m','—')}")
        cfg = z.get("behavior_config", {}).get("config", {})
        print(f"  speed_limit_kmh={cfg.get('speed_limit_kmh')}  cooldown={cfg.get('cooldown_sec')}")
