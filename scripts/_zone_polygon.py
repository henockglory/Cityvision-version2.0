#!/usr/bin/env python3
import subprocess, json

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

print("=== POLYGON Zone_distance_parcourue ===")
row = psql("SELECT polygon::text, behavior_config::text FROM zones WHERE name='Zone_distance_parcourue';")
if '|' in row:
    poly_raw, cfg_raw = row.split('|', 1)
    try:
        poly = json.loads(poly_raw)
        print(f"Polygon ({len(poly)} points):")
        for i, p in enumerate(poly):
            x, y = float(p.get('x',0)), float(p.get('y',0))
            d = p.get('distance_to_next_m')
            names = {0:'P0(top-left?)', 1:'P1(top-right?)', 2:'P2(bot-right?)', 3:'P3(bot-left?)'}
            print(f"  {names.get(i,f'P{i}')}: x={x:.4f} y={y:.4f} dist_to_next={d}m")
        ys = [float(p.get('y',0)) for p in poly]
        xs = [float(p.get('x',0)) for p in poly]
        top_y = min(ys)
        bot_y = max(ys)
        print(f"\n  → Zone height: y=[{top_y:.3f} → {bot_y:.3f}] = {bot_y-top_y:.3f} of frame height")
        print(f"  → Zone width:  x=[{min(xs):.3f} → {max(xs):.3f}]")
        print(f"\n  P0-P1 = LINE HAUT (sortie) : y≈{top_y:.3f}")
        print(f"  P2-P3 = LINE BAS  (entrée) : y≈{bot_y:.3f}")
        print(f"  → Distance verticale normalisée: {bot_y-top_y:.3f}")
    except Exception as e:
        print(f"Parse error: {e}")
        print(f"Raw: {poly_raw[:300]}")

    try:
        cfg = json.loads(cfg_raw)
        inner = cfg.get('config', cfg)
        print(f"\n=== BEHAVIOR CONFIG ===")
        print(f"  speed_limit_kmh = {inner.get('speed_limit_kmh')} {'(demo_force=ON ≤1km/h)' if float(inner.get('speed_limit_kmh',99))<=1 else ''}")
        print(f"  distance_m      = {inner.get('distance_m')}")
        print(f"  edge_distances_m= {inner.get('edge_distances_m')}")
        print(f"  cooldown_sec    = {inner.get('cooldown_sec','default(2s)')}")
        print(f"  class_filter    = {inner.get('class_filter')}")
    except Exception as e:
        print(f"Config parse error: {e}")
else:
    print("No row found")

print("\n=== EXPLANATION ===")
print("La vitesse est calculée ainsi:")
print("  1. Entrée: quand le centroid bas du véhicule entre dans le polygone")
print("     → enregistre (entry_time, entry_xy)")
print("  2. Sortie: quand il sort du polygone OU disparaît du tracker")
print("     → elapsed = exit_time - entry_time")
print("  3. distance_m = meters_per_norm_unit × norm_distance(entry_xy, exit_xy)")
print("     où meters_per_norm_unit vient des edge_distances_m calibrés")
print("  4. speed_kmh = distance_m / elapsed × 3.6")
print("  5. Si demo_force (limit≤1): tout speed>0 → alerte avec speed forcée à limit+1")
