#!/usr/bin/env python3
import subprocess, json

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

print("=== ZONE VITESSE CONFIG ===\n")

# Zone + behavior_config
row = psql("""
SELECT z.id, z.name,
       z.behavior_config::text,
       (SELECT json_agg(json_build_object('x',x_norm,'y',y_norm,'d',distance_to_next_m) ORDER BY vertex_order)
        FROM zone_vertices WHERE zone_id=z.id) as verts
FROM zones z
WHERE z.behavior ILIKE '%speed%' OR z.name ILIKE '%vitesse%' OR z.name ILIKE '%distance%'
LIMIT 1;
""")

if not row:
    print("Aucune zone speed trouvée!")
else:
    parts = row.split('|')
    print(f"ID: {parts[0]}")
    print(f"Nom: {parts[1]}")
    try:
        cfg = json.loads(parts[2]) if parts[2] else {}
        print(f"Config:")
        print(f"  limit_kmh: {cfg.get('speed_limit_kmh', 'N/A')}")
        print(f"  cooldown_sec: {cfg.get('cooldown_sec', 'N/A')}")
        print(f"  demo_force: {cfg.get('speed_limit_kmh', 99) <= 1}")
        edge_dists = cfg.get('edge_distances_m', [])
        print(f"  edge_distances_m: {edge_dists}")
        dist_m = cfg.get('distance_m')
        print(f"  distance_m: {dist_m}")
    except Exception as e:
        print(f"Config raw: {parts[2][:200]}")
    try:
        verts = json.loads(parts[3]) if parts[3] else []
        print(f"\nSommets ({len(verts)}):")
        for i, v in enumerate(verts):
            names = {0: "P0", 1: "P1", 2: "P2", 3: "P3"}
            print(f"  {names.get(i, f'P{i}')}: x={v.get('x','?'):.3f} y={v.get('y','?'):.3f} dist_to_next={v.get('d','N/A')}m")
        if len(verts) >= 4:
            # Zone height = entry line (P2-P3) y - exit line (P0-P1) y
            p0y = verts[0].get('y', 0)
            p1y = verts[1].get('y', 0)
            p2y = verts[2].get('y', 0)
            p3y = verts[3].get('y', 0)
            top_y = min(p0y, p1y)
            bot_y = max(p2y, p3y)
            print(f"\n  → Ligne HAUT (P0-P1): y≈{top_y:.3f}")
            print(f"  → Ligne BAS  (P2-P3): y≈{bot_y:.3f}")
            print(f"  → Hauteur zone: {bot_y - top_y:.3f} en coord norm")
            d_p2p3 = verts[2].get('d') if len(verts) > 2 else None
            d_p3p0 = verts[3].get('d') if len(verts) > 3 else None
            print(f"\n  distance P2→P3 (côté): {d_p2p3}m")
            print(f"  distance P3→P0 (traverse): {d_p3p0}m")
    except Exception as e:
        print(f"Vertices error: {e}")

# AI engine zone_speed config
print("\n=== ZONE SPEED DEBUG (last AI log) ===")
r = subprocess.run(
    ["bash", "-c", "grep 'zone_speed_debug' ~/citevision-v2/logs/ai-engine.log | tail -3"],
    capture_output=True, text=True)
print(r.stdout.strip())

# Recent speeding events frequency
print("\n=== FRÉQUENCE ÉVÉNEMENTS ===")
r2 = psql("""
SELECT to_char(occurred_at AT TIME ZONE 'Europe/Paris','HH24:MI:SS'),
       EXTRACT(EPOCH FROM (occurred_at - LAG(occurred_at) OVER (ORDER BY occurred_at))) as gap_sec
FROM events
WHERE event_type='speeding'
ORDER BY occurred_at DESC
LIMIT 10;
""")
print("Heure       | Gap depuis précédent (sec)")
for line in r2.split('\n'):
    if line:
        p = line.split('|')
        t = p[0] if p else ''
        g = f"{float(p[1]):.1f}s" if len(p) > 1 and p[1].strip() else 'premier'
        print(f"  {t}  |  {g}")
