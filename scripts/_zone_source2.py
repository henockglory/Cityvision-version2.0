#!/usr/bin/env python3
import subprocess, json, urllib.request

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

def get(url):
    try:
        return json.loads(urllib.request.urlopen(url, timeout=5).read())
    except:
        return None

print("=== ZONES TABLE (5 zones) ===")
rows = psql("SELECT id, name, behavior, LEFT(behavior_config::text,300) FROM zones;")
for row in rows.split('\n'):
    if row:
        p = row.split('|')
        print(f"  {p[0]} | {p[1]} | behavior={p[2]}")
        if len(p) > 3:
            try:
                cfg = json.loads(p[3])
                print(f"    -> limit={cfg.get('speed_limit_kmh')} dist={cfg.get('distance_m')} edges={cfg.get('edge_distances_m')}")
            except:
                pass

print("\n=== ZONE VERTICES ===")
verts_rows = psql("""
SELECT z.name, v.vertex_order, v.x_norm, v.y_norm, v.distance_to_next_m
FROM zone_vertices v
JOIN zones z ON z.id = v.zone_id
ORDER BY z.name, v.vertex_order;
""")
for row in verts_rows.split('\n'):
    if row:
        print(f"  {row}")

print("\n=== AI /cameras ENDPOINT (raw) ===")
try:
    data = urllib.request.urlopen("http://localhost:8001/cameras", timeout=5).read()
    d = json.loads(data)
    print(f"type={type(d).__name__}")
    if isinstance(d, dict):
        for cam_id, cam in d.items():
            zones = cam.get("zones") or []
            print(f"  cam={cam_id} zones={len(zones)}")
            for z in zones:
                poly = z.get("polygon") or []
                ys = [v.get("y",0) for v in poly]
                cfg = z.get("behavior_config") or {}
                verts = z.get("vertices") or []
                d_vals = [v.get("distance_to_next_m") for v in verts if v.get("distance_to_next_m") is not None]
                print(f"    {z.get('name')}: y=[{min(ys):.3f}-{max(ys):.3f}] limit={cfg.get('speed_limit_kmh')}km/h cooldown={cfg.get('cooldown_sec')}s dists={d_vals}")
    elif isinstance(d, list):
        for item in d:
            print(f"  item: {str(item)[:200]}")
except Exception as e:
    print(f"  Error: {e}")
