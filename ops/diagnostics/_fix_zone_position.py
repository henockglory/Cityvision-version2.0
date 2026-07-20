#!/usr/bin/env python3
"""
Reposition la zone de vitesse sur les coordonnées réelles des véhicules détectés.
Données observées : norm_bottom_y entre 0.06 et 0.29 → zone à y=[0.08, 0.32].
Arêtes verticales (côtés) = 8 m réels.
"""
import json, subprocess

ORG  = "e312f375-7442-4089-8022-ed232abc09e8"
ZONE = "Zone_distance_parcourue"

# Bande fine au centre du trafic visible (y de 0.08 à 0.32)
# Voitures entrent à y=0.32 (bas), sortent à y=0.08 (haut)
X_L   = 0.02
X_R   = 0.98
Y_TOP = 0.08   # ligne de sortie
Y_BOT = 0.32   # ligne d'entrée

polygon = [
    {"x": X_L, "y": Y_TOP},
    {"x": X_R, "y": Y_TOP, "distance_to_next_m": 8.0},
    {"x": X_R, "y": Y_BOT},
    {"x": X_L, "y": Y_BOT, "distance_to_next_m": 8.0},
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
    updated_at      = NOW()
WHERE org_id = '{ORG}'::uuid AND name = '{ZONE}';
"""

r = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres",
     "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
    capture_output=True, text=True,
)
print(r.stdout.strip())
if r.stderr.strip(): print("ERR:", r.stderr.strip())

# Vérification
r2 = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres",
     "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c",
     f"SELECT polygon::text FROM zones WHERE org_id='{ORG}'::uuid AND name='{ZONE}';"],
    capture_output=True, text=True,
)
stored = json.loads(r2.stdout.strip())
print(f"Zone repositionnée — {len(stored)} sommets :")
for i, p in enumerate(stored):
    d = p.get("distance_to_next_m", "—")
    print(f"  P{i} ({p['x']:.3f}, {p['y']:.3f})  dist={d}")
print(f"\nBande : y=[{Y_TOP}, {Y_BOT}] — hauteur={Y_BOT-Y_TOP:.2f} unités")
print(f"Echelle ≈ {8/(Y_BOT-Y_TOP):.0f} m/unité")
print("Les véhicules observés sont à y_bottom=[0.06-0.29] → zone maintenant au bon endroit")
