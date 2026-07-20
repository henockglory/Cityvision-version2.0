#!/usr/bin/env python3
"""Purge rapide toutes preuves — TRUNCATE DB + MinIO + Frigate recordings + clips."""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path.home() / "citevision-v2"
API = os.environ.get("API", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")


def run(cmd: list[str] | str, timeout: int = 600, check: bool = True) -> subprocess.CompletedProcess:
    if isinstance(cmd, str):
        return subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout, check=check)
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=check)


def psql(sql: str, timeout: int = 3600) -> str:
    r = run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-v", "ON_ERROR_STOP=1", "-c", sql],
        timeout=timeout,
        check=False,
    )
    if r.returncode != 0:
        print(f"[ERR] psql: {r.stderr.strip()[:500]}", file=sys.stderr)
        raise SystemExit(1)
    return r.stdout.strip()


def du_docker(path: str) -> str:
    r = run(["docker", "exec", "citevision-v2-minio", "du", "-sh", path], check=False, timeout=120)
    return (r.stdout or "?").split()[0] if r.stdout else "?"


def main() -> int:
    print("=== AVANT ===")
    print(psql("SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"))
    print(f"MinIO evidence: {du_docker('/data/citevision-evidence')}")

    print("\n=== Stop IA ===")
    for pat in ("citevision-ai", "run-ai-engine", "uvicorn citevision_ai"):
        subprocess.run(["pkill", "-f", pat], capture_output=True)
    time.sleep(2)

    print("\n=== TRUNCATE DB (rapide) ===")
    psql("TRUNCATE TABLE alerts RESTART IDENTITY CASCADE;", timeout=600)
    psql("TRUNCATE TABLE events RESTART IDENTITY CASCADE;", timeout=3600)
    r = run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c",
         "SELECT to_regclass('public.evidence_objects');"],
        check=False,
    )
    if (r.stdout or "").strip() == "evidence_objects":
        psql("TRUNCATE TABLE evidence_objects RESTART IDENTITY CASCADE;", timeout=600)
    psql("UPDATE rule_counters SET count=0, last_event_type='', updated_at=NOW();", timeout=120)
    psql("VACUUM ANALYZE alerts;", timeout=300)
    psql("VACUUM ANALYZE events;", timeout=300)

    print("\n=== Purge MinIO (65G+) ===")
    r = run(
        "docker exec citevision-v2-minio sh -c 'rm -rf /data/citevision-evidence && mkdir -p /data/citevision-evidence && echo done'",
        timeout=1800,
        check=False,
    )
    print(r.stdout or r.stderr)

    print("\n=== Purge Frigate recordings ===")
    run(
        "docker run --rm -v infra_frigate_recordings:/v alpine sh -c 'rm -rf /v/*; echo frigate cleared'",
        timeout=600,
        check=False,
    )

    print("\n=== Purge clips locaux ===")
    for base in [ROOT / "backend/data/clips", Path("/mnt/c/Users/gheno/citevision/backend/data/clips"), Path("/mnt/c/Citevision/backend/data/clips")]:
        if base.is_dir():
            for p in base.iterdir():
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    import shutil
                    shutil.rmtree(p, ignore_errors=True)
            print(f"  cleared {base}")

    print("\n=== Réactivation règles démo ===")
    try:
        login = json.loads(urllib.request.urlopen(
            urllib.request.Request(
                f"{API}/api/v1/auth/login",
                data=json.dumps({"email": EMAIL, "password": PASS}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=30,
        ).read().decode())
        token = login["access_token"]
        me = json.loads(urllib.request.urlopen(
            urllib.request.Request(f"{API}/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}),
            timeout=30,
        ).read().decode())
        org = me["org_id"]
        rules = json.loads(urllib.request.urlopen(
            urllib.request.Request(f"{API}/api/v1/orgs/{org}/rules", headers={"Authorization": f"Bearer {token}"}),
            timeout=60,
        ).read().decode())
        n = 0
        for rule in rules:
            if str(rule.get("name", "")).startswith("Démo") and not rule.get("is_enabled"):
                urllib.request.urlopen(
                    urllib.request.Request(
                        f"{API}/api/v1/orgs/{org}/rules/{rule['id']}",
                        data=json.dumps({"is_enabled": True}).encode(),
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        method="PATCH",
                    ),
                    timeout=30,
                )
                n += 1
                print(f"  enabled: {rule['name']}")
        psql("UPDATE rules SET is_enabled=true, updated_at=NOW() WHERE name LIKE 'Démo%';", timeout=60)
        print(f"  total enabled via API: {n}")
    except Exception as exc:
        print(f"  WARN rules re-enable: {exc}")

    print("\n=== Restart IA ===")
    subprocess.run(["python3", str(ROOT / "scripts/_restart_ai.py")], check=False)

    print("\n=== APRÈS ===")
    print(psql("SELECT 'alerts', count(*) FROM alerts UNION ALL SELECT 'events', count(*) FROM events;"))
    print(f"MinIO evidence: {du_docker('/data/citevision-evidence')}")
    r2 = run("docker run --rm -v infra_frigate_recordings:/v:ro alpine du -sh /v", check=False)
    print(f"Frigate recordings: {(r2.stdout or '?').strip()}")
    print("[OK] base vierge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
