#!/usr/bin/env python3
"""Diagnostic rapide : pourquoi les alertes sont bloquées."""
import json, subprocess, urllib.request, datetime

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

def get(url, key="changeme_internal_service_key"):
    try:
        req = urllib.request.Request(url, headers={"X-Internal-Key": key})
        return json.load(urllib.request.urlopen(req, timeout=5))
    except Exception as e:
        return {"error": str(e)}

print("=" * 60)
print("1. AI ENGINE HEALTH")
ai = get("http://127.0.0.1:8001/health")
print(json.dumps(ai, indent=2))

print("\n2. CAMERAS / FRAMES")
cams = get("http://127.0.0.1:8001/cameras")
for c in (cams.get("cameras") or []):
    print(f"  {c.get('camera_id')}  running={c.get('running')}  frames={c.get('frames_processed')}")

print("\n3. DERNIERS EVENTS VITESSE (10 derniers)")
rows = psql("""
  SELECT created_at, type, camera_id, payload->>'speed_kmh' as spd
  FROM events
  WHERE type='speeding'
  ORDER BY created_at DESC LIMIT 10;
""")
print(rows or "(aucun)")

print("\n4. DERNIÈRES ALERTES (10 dernières)")
rows2 = psql("""
  SELECT created_at, rule_id, evidence_snapshot IS NOT NULL as has_evidence
  FROM alerts
  ORDER BY created_at DESC LIMIT 10;
""")
print(rows2 or "(aucune)")

print("\n5. RULES ENGINE HEALTH")
re = get("http://127.0.0.1:8010/health")
print(json.dumps(re, indent=2))

print("\n6. RULES ACTIVES")
rules = get("http://127.0.0.1:8010/rules")
for r in (rules.get("rules") or []):
    print(f"  {r.get('rule_id')}  enabled={r.get('enabled')}  type={r.get('condition_type')}")

print("\n7. ZONE COOLDOWN ACTIF ? (events dans les 30 dernières secondes)")
recent = psql("""
  SELECT COUNT(*) FROM events
  WHERE type='speeding' AND created_at > NOW() - INTERVAL '30 seconds';
""")
print(f"  events speeding (30s) = {recent}")
