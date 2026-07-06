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

print("=== ZONES TABLE ===")
print(psql("SELECT count(*) FROM zones;"), "zones")

print("\n=== CAMERAS (zone config) ===")
cams_raw = psql("SELECT id, name, LEFT(zones::text, 400) FROM cameras LIMIT 3;")
for row in cams_raw.split('\n'):
    if row:
        p = row.split('|')
        print(f"  cam={p[0]} name={p[1]}")
        if len(p) > 2 and p[2]:
            try:
                z = json.loads(p[2])
                for zone in z:
                    poly = zone.get("polygon") or zone.get("vertices") or []
                    ys = [v.get("y", 0) for v in poly]
                    cfg = zone.get("behavior_config") or {}
                    print(f"    zone={zone.get('name')} poly_y=[{min(ys) if ys else '?':.2f}-{max(ys) if ys else '?':.2f}]"
                          f" limit={cfg.get('speed_limit_kmh')}km/h dist={cfg.get('distance_m')}m"
                          f" edges={cfg.get('edge_distances_m')}")
            except Exception as e:
                print(f"    parse error: {e} | raw: {p[2][:100]}")

print("\n=== AI /cameras ENDPOINT ===")
cams = get("http://localhost:8001/cameras") or get("http://localhost:8001/api/cameras")
if cams:
    for c in cams:
        cid = c.get("camera_id")
        zones = c.get("zones", [])
        print(f"  cam={cid} zones={len(zones)}")
        for z in zones:
            poly = z.get("polygon") or []
            ys = [v.get("y", 0) for v in poly]
            cfg = z.get("behavior_config") or {}
            verts = z.get("vertices") or []
            d_vals = [v.get("distance_to_next_m") for v in verts if v.get("distance_to_next_m")]
            print(f"    zone={z.get('name')} poly_y=[{min(ys) if ys else '?':.2f}-{max(ys) if ys else '?':.2f}]"
                  f" limit={cfg.get('speed_limit_kmh')}km/h cooldown={cfg.get('cooldown_sec')}s"
                  f" dist_m={cfg.get('distance_m')} edges={cfg.get('edge_distances_m')}"
                  f" vertex_dists={d_vals}")
else:
    print("  No /cameras endpoint")

print("\n=== BACKEND /internal/cameras ===")
r = subprocess.run(["bash", "-c",
    "curl -sf 'http://localhost:8081/internal/cameras' 2>/dev/null || echo 'no endpoint'"],
    capture_output=True, text=True)
try:
    d = json.loads(r.stdout)
    print(f"  {len(d)} cameras from backend")
except:
    print("  " + r.stdout[:200])
