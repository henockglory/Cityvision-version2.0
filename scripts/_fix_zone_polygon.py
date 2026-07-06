#!/usr/bin/env python3
"""Repositionne le polygon de la zone de vitesse là où les véhicules sont réellement dans le flux vidéo.

Diagnostic: tous les véhicules sont à y=0.02-0.06 (haut du cadre), la zone était à y=0.19-0.69.
Nouvelle zone: y=[0.01-0.12] couvrant le passage réel des véhicules.
"""
import subprocess, json

def psql(sql, params=None):
    cmd = ["docker", "exec", "citevision-v2-postgres",
           "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"PSQL error: {r.stderr.strip()}")
    return r.stdout.strip()

# Zone polygon: y=[0.01-0.13], width full road x=[0.10-0.90]
# Cars move BOTTOM→TOP, so:
#   P0 = top-left  (EXIT line)  y=0.01
#   P1 = top-right (EXIT line)  y=0.01
#   P2 = bot-right (ENTRY line) y=0.13
#   P3 = bot-left  (ENTRY line) y=0.13
# Each vertex has distance_to_next_m=100 (100m total, enables demo_force detection)
new_polygon = [
    {"x": 0.10, "y": 0.01, "distance_to_next_m": 100},  # P0 top-left (sortie)
    {"x": 0.90, "y": 0.01, "distance_to_next_m": 100},  # P1 top-right (sortie)
    {"x": 0.90, "y": 0.13, "distance_to_next_m": 100},  # P2 bot-right (entrée)
    {"x": 0.10, "y": 0.13, "distance_to_next_m": 100},  # P3 bot-left (entrée)
]

new_config = {
    "behavior": "speed_measurement",
    "config": {
        "distance_m": 100,
        "edge_distances_m": [100, 100, 100, 100],
        "speed_limit_kmh": 1,      # demo_force active (≤1 km/h)
        "cooldown_sec": 2.0,
        "spatial_dedup_sec": 2.0,
        "class_filter": "any",     # toutes classes (car, truck, bus...)
    }
}

poly_json = json.dumps(new_polygon)
cfg_json = json.dumps(new_config)

print("Mise à jour du polygon Zone_distance_parcourue...")
result = psql(f"""
UPDATE zones
SET polygon = '{poly_json}'::jsonb,
    behavior_config = '{cfg_json}'::jsonb,
    zone_kind = 'speed_measurement',
    is_active = true,
    updated_at = NOW()
WHERE name='Zone_distance_parcourue';
""")
print(f"  UPDATE result: {result}")

# Verify
row = psql("SELECT name, zone_kind, polygon::text, behavior_config::text FROM zones WHERE name='Zone_distance_parcourue';")
if '|' in row:
    parts = row.split('|')
    poly = json.loads(parts[2])
    cfg = json.loads(parts[3])
    inner = cfg.get('config', cfg)
    ys = [p['y'] for p in poly]
    print(f"\nVérification:")
    print(f"  Nom: {parts[0]}, zone_kind: {parts[1]}")
    print(f"  Polygon: y=[{min(ys):.3f}-{max(ys):.3f}]")
    for i, p in enumerate(poly):
        print(f"    P{i}: x={p['x']:.2f} y={p['y']:.2f} d={p.get('distance_to_next_m')}m")
    print(f"  Config: limit={inner.get('speed_limit_kmh')}km/h dist={inner.get('distance_m')}m filter={inner.get('class_filter')}")
    print(f"  demo_force: {float(inner.get('speed_limit_kmh', 99)) <= 1}")
    print("\n✓ Zone correctement repositionnée à y=[0.01-0.13]")
else:
    print("ERREUR: zone introuvable après update")
