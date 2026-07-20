#!/usr/bin/env python3
"""Vérification du schéma DB et état réel des données."""
import subprocess

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

print("1. TABLES existantes:")
print(psql("SELECT schemaname, tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"))

print("\n2. Colonnes de la table events:")
print(psql("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='events' ORDER BY ordinal_position;"))

print("\n3. Colonnes de la table alerts:")
print(psql("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='alerts' ORDER BY ordinal_position;"))

print("\n4. Count et sample events:")
print("total:", psql("SELECT COUNT(*) FROM events;"))
print("avec type non-null:", psql("SELECT COUNT(*) FROM events WHERE type IS NOT NULL;"))
print("avec created_at non-null:", psql("SELECT COUNT(*) FROM events WHERE created_at IS NOT NULL;"))
print("types distincts:", psql("SELECT DISTINCT type FROM events LIMIT 10;"))
print("sample events:", psql("SELECT id, org_id, type, created_at FROM events ORDER BY id DESC LIMIT 5;"))

print("\n5. Count et sample alerts:")
print("total:", psql("SELECT COUNT(*) FROM alerts;"))
print("sample alerts:", psql("SELECT id, rule_id, created_at FROM alerts ORDER BY id DESC LIMIT 5;"))

print("\n6. Backend logs (dernières lignes pertinentes):")
r = subprocess.run(
    ["bash", "-c", "tail -n 100 /home/gheno/citevision-v2/logs/backend.log 2>/dev/null | grep -iE 'mqtt|event|speeding|ingest|speed|error' | tail -20"],
    capture_output=True, text=True)
print(r.stdout.strip() or "(rien)")
