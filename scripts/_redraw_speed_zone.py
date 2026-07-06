#!/usr/bin/env python3
"""Redessine la zone vitesse là où les véhicules circulent RÉELLEMENT.

Analyse des logs AI :
  - Véhicules x : 0.39 – 0.65  (bande centrale-droite)
  - Véhicules y : 0.06 – 0.35  (haut de l'écran, coordonnées image)
  - Direction    : y décroît au fil du temps → les voitures montent (bas→haut)

Zone : bande fine horizontale centrée sur le flux réel.
  - ENTRÉE (bord bas)  : y = 0.30  (voitures entrent ici)
  - SORTIE (bord haut) : y = 0.07  (voitures sortent ici)
  - Largeur            : x 0.28 → 0.78  (marge de sécurité de chaque côté)

Arêtes calibrées : côtés VERTICAUX = 8 m réels (distance parcourue par un véhicule).
"""
import json, subprocess

ORG  = "e312f375-7442-4089-8022-ed232abc09e8"
ZONE = "Zone_distance_parcourue"

X_L   = 0.28
X_R   = 0.78
Y_TOP = 0.07   # ligne de sortie  (voitures quittent la bande ici)
Y_BOT = 0.30   # ligne d'entrée   (voitures entrent dans la bande ici)

# Polygone sens horaire : top-left → top-right → bottom-right → bottom-left
# distance_to_next_m sur les arêtes VERTICALES uniquement (gauche et droite)
polygon = [
    {"x": X_L, "y": Y_TOP},                              # P0 top-left    edge→P1 horizontal, non calibrée
    {"x": X_R, "y": Y_TOP, "distance_to_next_m": 8.0},  # P1 top-right   edge→P2 vertical = 8 m
    {"x": X_R, "y": Y_BOT},                              # P2 bottom-right edge→P3 horizontal, non calibrée
    {"x": X_L, "y": Y_BOT, "distance_to_next_m": 8.0},  # P3 bottom-left  edge→P0 vertical = 8 m
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
print(r.stdout.strip())
if r.stderr.strip():
    print("ERR:", r.stderr.strip())

# ── Vérification DB ────────────────────────────────────────────────────────
r2 = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres",
     "psql", "-U", "citevision", "-d", "citevision",
     "-t", "-A", "-c",
     f"SELECT polygon::text, behavior_config::text FROM zones "
     f"WHERE org_id='{ORG}'::uuid AND name='{ZONE}';"],
    capture_output=True, text=True)

parts = r2.stdout.strip().split("|")
poly  = json.loads(parts[0])
cfg   = json.loads(parts[1]).get("config", {})

print(f"\nZone mise à jour — {len(poly)} sommets :")
for i, p in enumerate(poly):
    d = p.get("distance_to_next_m", "—")
    print(f"  P{i} ({p['x']:.2f}, {p['y']:.2f})  distance_to_next_m={d}")

height = abs(poly[0]["y"] - poly[3]["y"])
print(f"\nHauteur bande : {height:.2f} unités  →  échelle ≈ {8/height:.1f} m/unité")
print(f"speed_limit_kmh  : {cfg.get('speed_limit_kmh')}")
print(f"distance_m       : {cfg.get('distance_m')}")
print(f"edge_distances_m : {cfg.get('edge_distances_m')}")
print(f"cooldown_sec     : {cfg.get('cooldown_sec')}")
print("\n[OK] Zone DB prête — restart AI à faire")
