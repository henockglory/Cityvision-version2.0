#!/usr/bin/env python3
"""Quick peek at alert evidence_snapshot shape + demo zones."""
import json
import subprocess

def q(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode:
        return "ERR " + (r.stderr or r.stdout)
    return r.stdout

print("=== demo cameras ===")
print(q("SELECT id::text, name FROM cameras WHERE name ILIKE '%Démo%' OR name ILIKE '%Demo%' OR name ILIKE '%Feux%' OR name ILIKE '%Ceinture%' OR name ILIKE '%Décompte%' OR name ILIKE '%Ligne Continue%' ORDER BY name;"))

print("=== zones ===")
print(q("""
SELECT c.name, z.name, z.zone_kind, LEFT(z.polygon::text, 120)
FROM zones z JOIN cameras c ON c.id=z.camera_id
WHERE c.name ILIKE '%Démo%' OR c.name ILIKE '%Demo%' OR c.name ILIKE '%Feux%' OR c.name ILIKE '%Ceinture%' OR c.name ILIKE '%Décompte%' OR c.name ILIKE '%Ligne%'
ORDER BY c.name, z.name;
"""))

print("=== lines ===")
print(q("""
SELECT c.name, l.name, l.start_point::text, l.end_point::text
FROM lines l JOIN cameras c ON c.id=l.camera_id
WHERE c.name ILIKE '%Démo%' OR c.name ILIKE '%Demo%' OR c.name ILIKE '%Décompte%' OR c.name ILIKE '%Ligne%'
ORDER BY c.name, l.name;
"""))

print("=== sample evidence_snapshot keys ===")
row = q("""
SELECT a.id::text, a.title, a.evidence_snapshot::text
FROM alerts a
WHERE a.created_at > NOW() - INTERVAL '72 hours'
  AND a.evidence_snapshot IS NOT NULL
  AND a.evidence_snapshot::text != 'null'
  AND a.evidence_snapshot::text != '{}'
ORDER BY a.created_at DESC LIMIT 1;
""")
print(row[:2000])
if "|" in row or "\t" in row or len(row) > 10:
    # parse: id|title|json or id\ntitle\njson depending on -A
    parts = row.strip().split("\n")
    for p in parts:
        if p.startswith("{"):
            try:
                d = json.loads(p)
                print("TOP_KEYS", list(d.keys())[:40])
                print(json.dumps(d, indent=2)[:2500])
            except Exception as e:
                print("parse fail", e, p[:200])
