#!/usr/bin/env python3
"""Set speed limit to 1 km/h for camera 108 test + resync + wait for 3 detections."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
ZONE_NAME = "Zone_distance_parcourue_108"
TARGET_LIMIT = 1.0


def load_env() -> None:
    for p in (ROOT / ".env", Path.home() / "citevision-v2" / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


load_env()
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
AI = os.environ.get("AI_HEALTH_URL", "http://127.0.0.1:8001")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")


def psql(sql: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
        capture_output=True,
        text=True,
    )
    return (proc.stdout or proc.stderr).strip()


def req(method: str, url: str, token: str | None = None, body: dict | None = None, headers: dict | None = None):
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def count_speeding_since(since_sql: str) -> int:
    out = psql(
        f"SELECT count(*) FROM events WHERE camera_id='{CAM108}' AND event_type='speeding' "
        f"AND occurred_at > {since_sql};"
    )
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def count_alerts_since(since_sql: str) -> int:
    out = psql(
        f"SELECT count(*) FROM alerts a JOIN events e ON e.id=a.event_id "
        f"WHERE e.camera_id='{CAM108}' AND e.event_type='speeding' AND a.created_at > {since_sql};"
    )
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def main() -> int:
    print("=== 1. Abaissement limite vitesse -> 1 km/h ===")

    # Zone DB: behavior_config.config.speed_limit_kmh
    print(psql(
        f"UPDATE zones SET behavior_config = jsonb_set("
        f"  COALESCE(behavior_config, '{{}}'::jsonb), "
        f"  '{{config,speed_limit_kmh}}', '{TARGET_LIMIT}'::jsonb, true), "
        f"updated_at = NOW() "
        f"WHERE camera_id = '{CAM108}' AND name = '{ZONE_NAME}';"
    ))

    # Rule bindings: speed_kmh (orchestrator overlay)
    print(psql(
        f"UPDATE rules SET definition = jsonb_set("
        f"  definition, '{{bindings,speed_kmh}}', '{TARGET_LIMIT}'::jsonb, true), "
        f"updated_at = NOW() "
        f"WHERE org_id = '{ORG}' AND is_enabled = TRUE "
        f"AND (definition->'condition'->>'value' = 'speeding' OR name ILIKE '%vitesse%');"
    ))

    print("\n=== Vérification DB ===")
    print(psql(
        f"SELECT name, behavior_config->'config'->>'speed_limit_kmh' FROM zones "
        f"WHERE camera_id='{CAM108}' AND name='{ZONE_NAME}';"
    ))
    print(psql(
        f"SELECT name, is_enabled, definition->'bindings'->>'speed_kmh' as speed_kmh "
        f"FROM rules WHERE org_id='{ORG}' AND name ILIKE '%vitesse%';"
    ))

    print("\n=== 2. Resync spatial vers AI ===")
    try:
        req(
            "POST",
            f"{API}/api/v1/internal/ingest/resync-spatial",
            headers={"X-Internal-Key": INTERNAL},
            body={},
        )
        print("[OK] resync-spatial")
    except urllib.error.HTTPError as e:
        try:
            req(
                "POST",
                f"{API}/api/v1/internal/resync-spatial",
                headers={"X-Internal-Key": INTERNAL},
                body={},
            )
            print("[OK] resync-spatial (alt endpoint)")
        except urllib.error.HTTPError:
            print(f"[WARN] resync HTTP {e.code}")
    time.sleep(8)

    spatial = req(
        "GET",
        f"{API}/api/v1/internal/ingest/orgs/{ORG}/cameras/{CAM108}/spatial-config",
        headers={"X-Internal-Key": INTERNAL},
    )
    for z in spatial.get("zones", []):
        if z.get("behavior") == "speed_measurement":
            cfg = (z.get("behavior_config") or {}).get("config") or z.get("behavior_config") or {}
            print(f"[INFO] AI spatial-config limit={cfg.get('speed_limit_kmh')} live_traffic={cfg.get('live_traffic')}")

    marker = "now()"
    baseline = count_speeding_since(marker)
    print(f"\n=== 3. Attente >= 3 nouvelles détections speeding (baseline={baseline}) ===")

    new_events = 0
    deadline = time.time() + 900  # 15 min max
    while time.time() < deadline:
        total = count_speeding_since(marker)
        new_events = total - baseline
        alerts_new = count_alerts_since(marker)
        cams = req("GET", f"{AI}/cameras")
        cam = next((c for c in cams.get("cameras", []) if c["camera_id"] == CAM108), {})
        print(
            f"  +{new_events} speeding | +{alerts_new} alertes | "
            f"processed={cam.get('frames_processed')} dropped={cam.get('frames_dropped')}"
        )
        if new_events >= 3:
            print("[OK] >= 3 détections atteintes")
            break
        time.sleep(30)
    else:
        print("[WARN] timeout 15 min — rapport avec données partielles")

    report = {
        "target_limit_kmh": TARGET_LIMIT,
        "new_speeding_events": new_events,
        "new_alerts": count_alerts_since(marker),
        "spatial": spatial,
    }
    out_path = ROOT / "scripts" / "_force_speed1_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[REPORT] {out_path}")

    # Run audit
    print("\n=== 4. Audit live ===")
    audit_py = Path.home() / "citevision-v2" / "ai-engine" / ".venv" / "bin" / "python3"
    if not audit_py.exists():
        audit_py = Path(sys.executable)
    proc = subprocess.run(
        [str(audit_py), str(ROOT / "scripts" / "audit_live_speed_camera.py")],
        cwd=str(Path.home() / "citevision-v2"),
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return 0 if new_events >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
