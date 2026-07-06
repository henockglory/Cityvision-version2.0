#!/usr/bin/env python3
import urllib.request, json

data = json.loads(urllib.request.urlopen("http://localhost:8001/cameras", timeout=5).read())
cameras = data.get("cameras", [])
print(f"{len(cameras)} cameras\n")
for cam in cameras:
    cam_id = cam.get("camera_id") or cam.get("id")
    zones = cam.get("zones") or []
    org = cam.get("org_id")
    print(f"cam={cam_id} org={org} zones={len(zones)}")
    for z in zones:
        poly = z.get("polygon") or z.get("vertices") or []
        ys = [float(v.get("y",0)) for v in poly]
        xs = [float(v.get("x",0)) for v in poly]
        cfg = z.get("behavior_config") or {}
        verts_detail = z.get("vertices") or []
        d_vals = [(v.get("distance_to_next_m"), i) for i,v in enumerate(verts_detail)]
        print(f"  zone={z.get('name')} behavior={z.get('behavior')}")
        print(f"    poly: x=[{min(xs):.3f}-{max(xs):.3f}] y=[{min(ys):.3f}-{max(ys):.3f}]")
        print(f"    config: limit={cfg.get('speed_limit_kmh')}km/h cooldown={cfg.get('cooldown_sec')}s")
        print(f"    distance_m={cfg.get('distance_m')} edge_distances_m={cfg.get('edge_distances_m')}")
        for i,v in enumerate(verts_detail):
            print(f"    P{i}: x={v.get('x',0):.4f} y={v.get('y',0):.4f} dist_to_next={v.get('distance_to_next_m')}m")
