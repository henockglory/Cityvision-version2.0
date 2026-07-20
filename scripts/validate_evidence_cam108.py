#!/usr/bin/env python3
"""Validation terrain preuves vitesse — caméra démo (lecture seule).

Résout la caméra via --camera-id ou --camera-name (API/DB), puis lance
audit_evidence_quality.py et vérifie les critères socle A.3 pour speeding.

Usage (WSL runtime ~/citevision-v2) :
  python3 scripts/validate_evidence_cam108.py --camera-name cam108 --limit 20
  python3 scripts/validate_evidence_cam108.py --camera-id <uuid> --check-mailhog

Conforme [P.135] : aucune écriture DB.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    for p in (ROOT / ".env", Path.home() / "citevision-v2" / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        break


def db_scalar(sql: str) -> str:
    cmd = [
        "docker", "exec", "citevision-v2-postgres",
        "psql", "-U", "citevision", "-d", "citevision",
        "-t", "-A", "-c", sql,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return res.stdout.strip()


def resolve_camera_id(name: str | None, explicit: str | None) -> str:
    if explicit:
        return explicit
    if not name:
        return ""
    safe = name.replace("'", "''")
    cid = db_scalar(
        f"SELECT id::text FROM cameras WHERE name ILIKE '%{safe}%' OR rtsp_url ILIKE '%{safe}%' LIMIT 1;"
    )
    return cid


def check_mailhog() -> bool:
    url = os.environ.get("MAILHOG_PUBLIC_URL", "http://localhost:8025")
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/v2/messages?limit=1", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        total = int(data.get("total") or 0)
        print(f"[mailhog] messages={total}")
        return total > 0
    except Exception as exc:
        print(f"[mailhog] indisponible: {exc}")
        return False


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description="Validation preuves speeding (terrain)")
    ap.add_argument("--camera-id", default="")
    ap.add_argument("--camera-name", default="108", help="Sous-chaîne nom/URL caméra (défaut 108)")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--check-mailhog", action="store_true")
    args = ap.parse_args()

    camera_id = resolve_camera_id(args.camera_name or None, args.camera_id or None)
    if not camera_id:
        print("[ERR] camera_id introuvable — passer --camera-id", file=sys.stderr)
        return 1
    print(f"==> validation camera_id={camera_id}")

    audit = ROOT / "scripts" / "audit_evidence_quality.py"
    cmd = [
        sys.executable, str(audit),
        "--camera-id", camera_id,
        "--limit", str(args.limit),
        "--event-type", "speeding",
    ]
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        return proc.returncode

    csv_path = ROOT / "scripts" / "evidence_audit_report.csv"
    if not csv_path.exists():
        print("[WARN] rapport CSV absent")
        return 1

    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    fresh = [r for r in rows if r.get("capture_source") == "frigate_track"]
    ok = [r for r in fresh if r.get("class") == "OK"]
    h5 = [r for r in rows if r.get("class") == "H5"]

    print("=== CRITERES A.3 (speeding) ===")
    print(json.dumps({
        "camera_id": camera_id,
        "total_audited": len(rows),
        "frigate_track": len(fresh),
        "ok_frigate_track": len(ok),
        "h5_misalign": len(h5),
        "frigate_event_id_populated": sum(1 for r in fresh if r.get("frigate_event_id")),
    }, indent=2))

    if args.check_mailhog:
        check_mailhog()

    if not fresh:
        print("[WARN] aucune preuve frigate_track — activer FRIGATE_ENABLED=1 EVIDENCE_BACKEND=frigate")
        return 2
    if len(ok) == 0:
        print("[FAIL] aucune preuve OK sur frigate_track récent")
        return 2
    print("[OK] au moins une preuve frigate_track valide")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
