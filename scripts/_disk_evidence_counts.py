#!/usr/bin/env python3
import subprocess

def psql(sql):
    return subprocess.check_output(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-c", sql],
        text=True,
    ).strip()

for label, sql in [
    ("alerts", "SELECT count(*) FROM alerts;"),
    ("events", "SELECT count(*) FROM events;"),
    ("evidence_tables", "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '%evid%';"),
]:
    try:
        print(label, psql(sql))
    except Exception as e:
        print(label, "ERR", e)

import glob, os, subprocess as sp
base = "/var/lib/docker/volumes/infra_minio_data/_data/citevision-evidence/orgs/*/cameras/*"
paths = sorted(glob.glob(base))
print("--- per camera (sudo du) ---")
for p in paths:
    out = sp.run(["sudo", "du", "-sh", p], capture_output=True, text=True)
    if out.stdout.strip():
        print(out.stdout.strip())
