#!/usr/bin/env python3
"""Diagnostic rapide : état AI, events récents, alertes récentes, rules-engine."""
import json, urllib.request, subprocess, datetime

API   = "http://127.0.0.1:8081"
AI    = "http://127.0.0.1:8001"
RULES = "http://127.0.0.1:8010"
KEY   = "changeme_internal_service_key"

def get(url, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        return json.load(urllib.request.urlopen(req, timeout=5))
    except Exception as e:
        return {"_error": str(e)}

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=10)
    return r.stdout.strip()

print("=" * 60)
print("SANTÉ DES SERVICES")
print("=" * 60)

ai_h = get(f"{AI}/health")
print(f"AI health    : {ai_h}")

rules_h = get(f"{RULES}/health")
print(f"Rules health : {rules_h}")

api_h = get(f"{API}/health")
print(f"API health   : {api_h}")

print()
print("=" * 60)
print("AI — FRAMES ET CAMÉRAS")
print("=" * 60)
cams = get(f"{AI}/cameras")
for c in (cams.get("cameras") or []):
    print(f"  cam {c.get('camera_id','?')[:20]}  running={c.get('running')}  frames={c.get('frames_processed')}  fps={c.get('fps')}")

print()
print("=" * 60)
print("EVENTS RÉCENTS (DB — 10 dernières minutes)")
print("=" * 60)
rows = psql("""
  SELECT to_char(created_at,'HH24:MI:SS'), type, speed_kmh, evidence_status
  FROM events
  WHERE created_at > NOW() - INTERVAL '10 minutes'
  ORDER BY created_at DESC
  LIMIT 15;
""")
print(rows if rows else "(aucun événement)")

print()
print("=" * 60)
print("ALERTES RÉCENTES (DB — 10 dernières minutes)")
print("=" * 60)
rows2 = psql("""
  SELECT to_char(a.created_at,'HH24:MI:SS'), a.rule_id,
         LEFT(a.evidence_snapshot::text, 60)
  FROM alerts a
  WHERE a.created_at > NOW() - INTERVAL '10 minutes'
  ORDER BY a.created_at DESC
  LIMIT 10;
""")
print(rows2 if rows2 else "(aucune alerte)")

print()
print("=" * 60)
print("DERNIÈRE ALERTE EN BASE")
print("=" * 60)
last = psql("""
  SELECT to_char(created_at,'YYYY-MM-DD HH24:MI:SS'), rule_id
  FROM alerts ORDER BY created_at DESC LIMIT 3;
""")
print(last if last else "(aucune alerte en base)")

print()
print("=" * 60)
print("RÈGLE VITESSE — LIMITE ACTUELLE")
print("=" * 60)
rule = psql("""
  SELECT name, is_active, definition::text
  FROM rules
  WHERE name ILIKE '%vitesse%' OR name ILIKE '%speed%' OR name ILIKE '%excès%'
  LIMIT 3;
""")
print(rule if rule else "(aucune règle vitesse)")
