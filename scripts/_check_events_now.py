#!/usr/bin/env python3
import subprocess, json

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=10)
    return r.stdout.strip()

print("=== EVENTS (5 dernières minutes) ===")
print(psql("""
  SELECT to_char(created_at,'HH24:MI:SS'), type, speed_kmh, evidence_status
  FROM events
  WHERE created_at > NOW() - INTERVAL '5 minutes'
  ORDER BY created_at DESC LIMIT 20;
""") or "(aucun)")

print()
print("=== DERNIERS EVENTS EN BASE ===")
print(psql("""
  SELECT to_char(created_at,'YYYY-MM-DD HH24:MI:SS'), type, speed_kmh
  FROM events ORDER BY created_at DESC LIMIT 5;
""") or "(table vide)")

print()
print("=== ALERTES (5 dernières minutes) ===")
print(psql("""
  SELECT to_char(created_at,'HH24:MI:SS'), rule_id
  FROM alerts
  WHERE created_at > NOW() - INTERVAL '5 minutes'
  ORDER BY created_at DESC LIMIT 10;
""") or "(aucune)")
