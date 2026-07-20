#!/usr/bin/env python3
"""Probe speed zone config + recent speeding events."""
import json
import subprocess
import sys


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
    return r.stdout.strip()


print("=== Zone_distance_parcourue ===")
row = psql(
    """
    SELECT z.id::text, z.name, z.camera_id::text, z.behavior_config::text, z.polygon::text
    FROM zones z WHERE z.name='Zone_distance_parcourue' LIMIT 1;
    """
)
if row:
    parts = row.split("|", 4)
    print(f"zone_id={parts[0]}")
    print(f"camera_id={parts[2]}")
    try:
        cfg = json.loads(parts[3]) if len(parts) > 3 else {}
        print(f"behavior_config={json.dumps(cfg, ensure_ascii=False)}")
    except json.JSONDecodeError:
        print(f"behavior_config_raw={parts[3][:500]}")
    if len(parts) > 4:
        try:
            poly = json.loads(parts[4])
            ys = [float(p.get("y", 0)) for p in poly]
            print(f"polygon_y=[{min(ys):.3f}-{max(ys):.3f}] verts={len(poly)}")
            print(f"distance_to_next={[p.get('distance_to_next_m') for p in poly]}")
        except Exception as e:
            print(f"polygon_error={e} poly={parts[4][:300]}")

print("\n=== Speed rule ===")
print(psql("SELECT name, is_enabled FROM rules WHERE name ILIKE '%vitesse%' OR name ILIKE '%Excès%';"))

print("\n=== Demo settings ===")
print(psql("SELECT org_id::text, active_camera_id::text, active_video_id::text, source_mode FROM org_demo_settings;"))

print("\n=== Speeding events last 2h ===")
print(psql(
    """
    SELECT COUNT(*) FROM events e
    WHERE e.occurred_at > NOW() - INTERVAL '2 hours'
      AND e.event_type = 'speeding';
    """
))

print("\n=== Last 5 speeding ===")
print(psql(
    """
    SELECT e.occurred_at::text, e.payload->>'speed_kmh', e.payload->>'zone_id',
           e.payload->'metadata'->>'method'
    FROM events e
    WHERE e.event_type = 'speeding'
    ORDER BY e.occurred_at DESC LIMIT 5;
    """
))
