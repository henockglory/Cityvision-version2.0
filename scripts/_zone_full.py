#!/usr/bin/env python3
import subprocess, json

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

# All zones
print("=== TOUTES LES ZONES ===")
rows = psql("SELECT id, name, behavior, behavior_config::text FROM zones ORDER BY created_at;")
for row in rows.split('\n'):
    if row:
        p = row.split('|')
        print(f"  ID={p[0]} | name={p[1]} | behavior={p[2]}")

print("\n=== ZONE Zone_distance_parcourue VERTICES ===")
row = psql("""
SELECT z.id, z.name, z.behavior_config::text,
       (SELECT json_agg(json_build_object('x',x_norm,'y',y_norm,'d',distance_to_next_m,'i',vertex_order) ORDER BY vertex_order)
        FROM zone_vertices WHERE zone_id=z.id) as verts
FROM zones z
WHERE z.name='Zone_distance_parcourue'
LIMIT 1;
""")
if row:
    p = row.split('|')
    print(f"ID: {p[0]}, Nom: {p[1]}")
    try:
        cfg = json.loads(p[2]) if p[2] else {}
        print(f"Config: limit={cfg.get('speed_limit_kmh')}km/h cooldown={cfg.get('cooldown_sec')}s")
        print(f"  edge_distances_m: {cfg.get('edge_distances_m')}")
        print(f"  distance_m: {cfg.get('distance_m')}")
    except:
        print(f"Config raw: {p[2][:300]}")
    try:
        verts = json.loads(p[3]) if p[3] else []
        print(f"\nVertices ({len(verts)}):")
        for v in verts:
            print(f"  P{v['i']}: x={v['x']:.4f} y={v['y']:.4f}  dist_to_next={v['d']}m")

        # Calculate zone dimensions
        if len(verts) >= 4:
            ys = [v['y'] for v in verts]
            xs = [v['x'] for v in verts]
            print(f"\n  Zone bounds: x=[{min(xs):.3f}-{max(xs):.3f}]  y=[{min(ys):.3f}-{max(ys):.3f}]")
            print(f"  Height (normalized): {max(ys)-min(ys):.3f}")
            print(f"  Width (normalized): {max(xs)-min(xs):.3f}")

            # Find the 'traverse distance' (vertical travel)
            # P0,P1 = top line  P2,P3 = bottom line (or reversed)
            sorted_by_y = sorted(verts, key=lambda v: v['y'])
            top2 = sorted_by_y[:2]
            bot2 = sorted_by_y[2:]
            print(f"\n  Ligne ENTRÉE (bas): y={sorted([v['y'] for v in bot2])}")
            print(f"  Ligne SORTIE (haut): y={sorted([v['y'] for v in top2])}")
            d_values = [v['d'] for v in verts if v['d'] is not None]
            print(f"\n  Distances calibrées: {d_values}")
    except Exception as e:
        print(f"Vertices error: {e}: raw={p[3][:200]}")

print("\n=== RÈGLE VITESSE (rules) ===")
r2 = psql("SELECT id, name, conditions::text FROM rules WHERE name ILIKE '%vitesse%' OR name ILIKE '%speed%';")
print(r2[:500])
