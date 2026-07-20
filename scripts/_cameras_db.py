#!/usr/bin/env python3
import subprocess, json

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

print("=== CAMERAS IN DB ===")
rows = psql("SELECT id, name, org_id FROM cameras;")
for row in rows.split('\n'):
    if row:
        p = row.split('|')
        print(f"  {p[0]} | org={p[2]} | name={p[1]}")

print("\n=== CAMERA ZONES COLUMN ===")
rows2 = psql("SELECT id, zones::text FROM cameras LIMIT 3;")
for row in rows2.split('\n'):
    if row and '|' in row:
        p = row.split('|', 1)
        print(f"cam={p[0]}")
        zones_raw = p[1] if len(p) > 1 else ''
        if zones_raw and zones_raw != 'null':
            try:
                zones = json.loads(zones_raw)
                print(f"  {len(zones)} zones")
                for z in zones:
                    poly = z.get('polygon') or []
                    ys = [float(v.get('y',0)) for v in poly]
                    cfg = z.get('behavior_config') or {}
                    print(f"  zone={z.get('name')} y=[{min(ys):.3f}-{max(ys):.3f}] limit={cfg.get('speed_limit_kmh')} dist={cfg.get('distance_m')}")
                    verts = z.get('vertices') or []
                    for i,v in enumerate(verts):
                        print(f"    P{i}: x={v.get('x',0):.4f} y={v.get('y',0):.4f} d={v.get('distance_to_next_m')}m")
            except Exception as e:
                print(f"  Error: {e} | raw: {zones_raw[:200]}")
        else:
            print(f"  zones=null/empty")

print("\n=== ZONES TABLE (separate) ===")
rows3 = psql("SELECT id, name, behavior FROM zones;")
for row in rows3.split('\n'):
    if row:
        print(f"  {row}")
