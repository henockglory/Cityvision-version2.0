#!/usr/bin/env python3
"""
Diagnostic et fix:
1. Vérifie les valeurs valides de l'enum event_severity
2. Vérifie ce que le moteur IA envoie comme severity pour les events speeding
3. Corrige le code si nécessaire
"""
import subprocess, json

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

print("1. Valeurs valides de l'enum event_severity:")
vals = psql("""
  SELECT enumlabel FROM pg_enum
  WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'event_severity')
  ORDER BY enumsortorder;
""")
print(vals or "(aucune)")

print("\n2. Valeurs valides de l'enum alert_severity (si différent):")
vals2 = psql("""
  SELECT enumlabel FROM pg_enum
  WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'alert_severity')
  ORDER BY enumsortorder;
""")
print(vals2 or "(même enum ou pas d'alert_severity)")

print("\n3. Quels types d'events arrivent en erreur dans les logs backend:")
r = subprocess.run(
    ["bash", "-c",
     "grep 'event ingest failed' /home/gheno/citevision-v2/logs/backend.log | "
     "grep -oP '\"type\":\"[^\"]+\"' | sort | uniq -c | sort -rn | head -10"],
    capture_output=True, text=True)
print(r.stdout.strip())

print("\n4. Severity envoyée par le moteur IA dans _make_speeding_event:")
r2 = subprocess.run(
    ["bash", "-c",
     "grep -n 'severity\\|speeding\\|critical\\|warning\\|info' "
     "/home/gheno/citevision-v2/ai-engine/src/citevision_ai/analytics/zone_speed.py | head -15"],
    capture_output=True, text=True)
print(r2.stdout.strip())

print("\n5. Vérifier le dernier backend.log pour les events speeding:")
r3 = subprocess.run(
    ["bash", "-c",
     "grep -i 'speeding' /home/gheno/citevision-v2/logs/backend.log | tail -5"],
    capture_output=True, text=True)
print(r3.stdout.strip() or "(aucun event speeding dans les logs)")
