#!/usr/bin/env python3
import subprocess

def q(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    return (r.stdout or "") + (("\nERR:" + r.stderr) if r.returncode else "")

for t in ("zones", "lines", "alerts", "events", "evidence_assets", "evidence_packages"):
    print("===", t)
    print(q(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}' ORDER BY ordinal_position;"))
