#!/usr/bin/env python3
"""Vérifie les events directement en DB et dans les logs AI."""
import subprocess, json, urllib.request

# 1. Events dans la DB (direct PostgreSQL)
r = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres",
     "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c",
     "SELECT event_type, created_at FROM events ORDER BY created_at DESC LIMIT 5;"],
    capture_output=True, text=True
)
print("=== Events DB (5 derniers) ===")
lines = r.stdout.strip().splitlines()
if lines:
    for l in lines: print(" ", l)
else:
    print("  (aucun)")

# 2. Events dans les logs AI (mqtt publish)
r2 = subprocess.run(
    ["grep", "-E", "speeding|publish.*event|mqtt.*event|zone_speed.*emitting|_make_speed",
     "/home/gheno/citevision-v2/logs/ai-engine.log"],
    capture_output=True, text=True
)
print(f"=== AI logs speeding/mqtt ({len(r2.stdout.splitlines())} lignes) ===")
for l in r2.stdout.strip().splitlines()[-10:]:
    print(" ", l[-120:])

# 3. MQTT broker - messages récents
r3 = subprocess.run(
    ["docker", "exec", "citevision-v2-mosquitto",
     "cat", "/var/log/mosquitto/mosquitto.log"],
    capture_output=True, text=True
)
lines3 = r3.stdout.strip().splitlines()
recent = [l for l in lines3 if 'PUBLISH' in l or 'event' in l.lower()]
print(f"=== MQTT logs PUBLISH ({len(recent)} lignes) ===")
for l in recent[-5:]: print(" ", l[-120:])
