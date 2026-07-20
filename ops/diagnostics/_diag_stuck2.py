#!/usr/bin/env python3
"""Diagnostic approfondi : events, alerts, tables, AI zone reload."""
import json, subprocess, urllib.request

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

def get(url):
    try:
        req = urllib.request.Request(url, headers={"X-Internal-Key": "changeme_internal_service_key"})
        return json.load(urllib.request.urlopen(req, timeout=5))
    except Exception as e:
        return {"error": str(e)}

print("1. TABLES EVENTS / ALERTS")
print(psql("SELECT COUNT(*) FROM events;") or "no events table")
print(psql("SELECT COUNT(*) FROM alerts;") or "no alerts table")
print(psql("SELECT type, COUNT(*) FROM events GROUP BY type ORDER BY 2 DESC LIMIT 10;"))
print(psql("SELECT MAX(created_at) FROM events;"))
print(psql("SELECT MAX(created_at) FROM alerts;"))

print("\n2. DERNIERS EVENTS TOUTES CATÉGORIES (10)")
print(psql("SELECT created_at, type FROM events ORDER BY created_at DESC LIMIT 10;") or "(aucun)")

print("\n3. AI CONFIG ZONE - RECHARGEMENT ?")
# Check the AI cameras endpoint for zone info
cams = get("http://127.0.0.1:8001/cameras")
print(json.dumps(cams, indent=2))

print("\n4. AI LOGS ZONE SPEED (50 dernières lignes)")
r = subprocess.run(
    ["wsl", "bash", "-c",
     "tail -n 100 /home/citevision/citevision-v2/logs/ai-engine.log 2>/dev/null | grep -i 'zone\\|speed\\|spatial\\|resync\\|reload\\|ingest' | tail -30"],
    capture_output=True, text=True, cwd="/"
)
print(r.stdout.strip() or "(pas de logs pertinents)")

print("\n5. MQTT - Y A-T-IL DES PUBLICATIONS RÉCENTES ?")
r2 = subprocess.run(
    ["wsl", "bash", "-c",
     "tail -n 50 /home/citevision/citevision-v2/logs/ai-engine.log 2>/dev/null | grep -i 'publish\\|mqtt\\|event' | tail -20"],
    capture_output=True, text=True, cwd="/"
)
print(r2.stdout.strip() or "(rien)")
