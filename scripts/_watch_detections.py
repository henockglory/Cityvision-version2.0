#!/usr/bin/env python3
"""Surveille les nouvelles détections en temps réel sur 30 secondes."""
import subprocess, json, time

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

# État avant
before_speed = int(psql("SELECT count(*) FROM events WHERE event_type='speeding';") or "0")
before_alerts = int(psql("SELECT count(*) FROM alerts;") or "0")
print(f"Avant  → speeding={before_speed}  alerts={before_alerts}")
print("Attente 30 secondes...")

time.sleep(30)

after_speed  = int(psql("SELECT count(*) FROM events WHERE event_type='speeding';") or "0")
after_alerts = int(psql("SELECT count(*) FROM alerts;") or "0")

print(f"Après  → speeding={after_speed}  alerts={after_alerts}")
print(f"Delta  → +{after_speed - before_speed} détections  +{after_alerts - before_alerts} alertes")

print()
print("=== 5 dernières détections ===")
rows = psql("""
  SELECT event_type,
         round((payload->>'speed_kmh')::numeric) as kmh,
         ingested_at
  FROM events
  WHERE event_type='speeding'
  ORDER BY ingested_at DESC LIMIT 5;
""")
print(rows or "(aucune)")

print()
print("=== 3 dernières alertes ===")
rows2 = psql("""
  SELECT rule_id, created_at, metadata->>'demo'
  FROM alerts
  ORDER BY created_at DESC LIMIT 3;
""")
print(rows2 or "(aucune)")
