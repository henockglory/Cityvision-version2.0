#!/usr/bin/env python3
"""Vérification complète de la chaîne AI → MQTT → Backend → DB."""
import subprocess, json

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

print("1. EVENTS (avec bonnes colonnes) - derniers 10:")
print(psql("""
  SELECT occurred_at, event_type, camera_id
  FROM events ORDER BY occurred_at DESC LIMIT 10;
""") or "(aucun)")

print("\n2. Events par type:")
print(psql("""
  SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY 2 DESC LIMIT 10;
""") or "(aucun)")

print("\n3. Derniers events speeding:")
print(psql("""
  SELECT occurred_at, event_type, payload->>'speed_kmh' as spd
  FROM events WHERE event_type='speeding'
  ORDER BY occurred_at DESC LIMIT 5;
""") or "(aucun speeding)")

print("\n4. MQTT - est-ce que les messages arrivent au backend ?")
r = subprocess.run(
    ["bash", "-c",
     "grep -i 'mqtt\\|subscriber\\|event ingest\\|speeding' /home/gheno/citevision-v2/logs/backend.log 2>/dev/null | tail -20"],
    capture_output=True, text=True)
print(r.stdout.strip() or "(rien)")

print("\n5. AI ENGINE - génère-t-il des events speeding dans SES logs ?")
r2 = subprocess.run(
    ["bash", "-c",
     "tail -n 500 /home/gheno/citevision-v2/logs/ai-engine.log | grep -iE 'speeding|speed_event|publish|mqtt|event_id' | tail -15"],
    capture_output=True, text=True)
print(r2.stdout.strip() or "(aucun log speeding)")

print("\n6. MQTT broker status:")
r3 = subprocess.run(
    ["bash", "-c", "docker ps | grep -i mqtt"],
    capture_output=True, text=True)
print(r3.stdout.strip() or "(pas de container MQTT trouvé)")

print("\n7. MQTT port test:")
r4 = subprocess.run(
    ["bash", "-c", "timeout 2 bash -c '</dev/tcp/localhost/1883' && echo 'MQTT port 1883 OPEN' || echo 'MQTT port 1883 CLOSED'"],
    capture_output=True, text=True)
print(r4.stdout.strip())
