#!/usr/bin/env python3
import subprocess

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=10)
    return r.stdout.strip()

print("=== event_severity enum values ===")
print(psql("""
  SELECT enumlabel FROM pg_enum
  JOIN pg_type ON pg_enum.enumtypid=pg_type.oid
  WHERE pg_type.typname='event_severity'
  ORDER BY enumsortorder;
"""))

print()
print("=== backend logs: speeding events specifically ===")
r = subprocess.run(
    ["wsl", "bash", "-c",
     "grep -i speeding /home/gheno/citevision-v2/logs/backend.log 2>/dev/null | tail -10"],
    capture_output=True, text=True, timeout=10)
print(r.stdout.strip() or "(aucun)")

print()
print("=== events table: count by type ===")
print(psql("SELECT type, COUNT(*) FROM events GROUP BY type ORDER BY COUNT(*) DESC;"))
print("(vide si 0 rows)")
