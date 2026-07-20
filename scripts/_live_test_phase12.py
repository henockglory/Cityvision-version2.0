#!/usr/bin/env python3
"""Phases 1-2 validation probe for camera 108 live test."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


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
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
CAMERA_MATCH = "192.168.1.108"


def req(method: str, url: str, token: str | None = None, body: dict | None = None, headers: dict | None = None) -> Any:
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


def psql(sql: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
    )
    return (proc.stdout or proc.stderr).strip()


def main() -> int:
    print("=== PHASE 1 — Règle → zone + policy preuves ===")
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login.get("access_token")
    if not token:
        print("[FAIL] login")
        return 1
    me = req("GET", f"{API}/api/v1/auth/me", token=token)
    org_id = str(me.get("org_id") or "")
    print(f"[OK] org_id={org_id}")

    try:
        spatial = req(
            "GET",
            f"{API}/api/v1/internal/ingest/orgs/{org_id}/cameras/{CAM108}/spatial-config",
            headers={"X-Internal-Key": INTERNAL},
        )
    except urllib.error.HTTPError as e:
        print(f"[FAIL] spatial-config HTTP {e.code}")
        return 1

    zones = spatial.get("zones") or []
    speed_zones = [z for z in zones if z.get("behavior") == "speed_measurement"]
    print(f"[INFO] zones speed_measurement: {len(speed_zones)}")
    phase1_ok = True
    for z in speed_zones:
        cfg = (z.get("behavior_config") or {}).get("config") or z.get("behavior_config") or {}
        limit = cfg.get("speed_limit_kmh")
        live = cfg.get("live_traffic")
        cooldown = cfg.get("cooldown_sec")
        print(f"  zone={z.get('zone_id') or z.get('name')} limit={limit} live_traffic={live} cooldown={cooldown}")
        if limit is None:
            phase1_ok = False

    rule_row = psql(
        "SELECT is_enabled, definition->'evidence'->'images'->1->>'crop', "
        "definition->'bindings'->>'live_traffic', definition->'bindings'->>'speed_limit_kmh' "
        "FROM rules WHERE camera_id='" + CAM108 + "' AND (definition->'condition'->>'value'='speeding' "
        "OR definition->'bindings'->>'template_id' LIKE '%speed%') ORDER BY updated_at DESC LIMIT 1;"
    )
    print(f"[INFO] rule DB row: {rule_row}")
    if "bbox" not in rule_row:
        print("[WARN] subject crop may not be bbox in DB rule")
        phase1_ok = False
    if "t|f" in rule_row or "|f|" in rule_row or rule_row.startswith("f|"):
        print("[WARN] rule may be disabled (is_enabled=false)")
    print("[OK] Phase 1" if phase1_ok else "[WARN] Phase 1 incomplete")

    ai_spatial = req("GET", f"{AI}/cameras/{CAM108}/spatial")
    print(f"[INFO] AI spatial: {json.dumps(ai_spatial)}")

    print("\n=== PHASE 2 — Observation 5 min (métriques + événements) ===")
    events_before = req("GET", f"{API}/api/v1/orgs/{org_id}/events?limit=200&event_type=speeding", token=token)
    if isinstance(events_before, dict):
        events_before = events_before.get("items", [])
    speed_before = len(events_before) if isinstance(events_before, list) else 0

    alerts_before = req("GET", f"{API}/api/v1/orgs/{org_id}/alerts?limit=50", token=token)
    if isinstance(alerts_before, dict):
        alerts_before = alerts_before.get("items", [])
    alerts_count_before = len(alerts_before) if isinstance(alerts_before, list) else 0

    cams0 = {c["camera_id"]: c for c in req("GET", f"{AI}/cameras").get("cameras", [])}
    fp0 = int(cams0.get(CAM108, {}).get("frames_processed", 0))
    fd0 = int(cams0.get(CAM108, {}).get("frames_dropped", 0))

    for minute in range(1, 6):
        time.sleep(60)
        cams = {c["camera_id"]: c for c in req("GET", f"{AI}/cameras").get("cameras", [])}
        gpu = req("GET", f"{AI}/health/gpu")
        cam = cams.get(CAM108, {})
        print(
            f"  min {minute}: processed={cam.get('frames_processed')} dropped={cam.get('frames_dropped')} "
            f"queue={cam.get('queue_depth')} latency_ms={cam.get('infer_latency_ms')} "
            f"gpu_drops={gpu.get('total_frames_dropped')}"
        )

    cams1 = {c["camera_id"]: c for c in req("GET", f"{AI}/cameras").get("cameras", [])}
    fp1 = int(cams1.get(CAM108, {}).get("frames_processed", 0))
    fd1 = int(cams1.get(CAM108, {}).get("frames_dropped", 0))
    delta_fp = fp1 - fp0
    delta_fd = fd1 - fd0

    events_after = req("GET", f"{API}/api/v1/orgs/{org_id}/events?limit=200&event_type=speeding", token=token)
    if isinstance(events_after, dict):
        events_after = events_after.get("items", [])
    speed_after = len(events_after) if isinstance(events_after, list) else 0

    alerts_after = req("GET", f"{API}/api/v1/orgs/{org_id}/alerts?limit=50", token=token)
    if isinstance(alerts_after, dict):
        alerts_after = alerts_after.get("items", [])
    alerts_count_after = len(alerts_after) if isinstance(alerts_after, list) else 0

    db_events = psql(
        f"SELECT count(*) FROM events WHERE camera_id='{CAM108}' AND event_type='speeding' "
        "AND created_at > now() - interval '10 minutes';"
    )
    db_alerts = psql(
        f"SELECT count(*) FROM alerts WHERE camera_id='{CAM108}' "
        "AND created_at > now() - interval '10 minutes';"
    )

    print(f"[INFO] 5min delta: frames_processed +{delta_fp}, frames_dropped +{delta_fd}")
    print(f"[INFO] API speeding events listed: {speed_before} -> {speed_after}")
    print(f"[INFO] API alerts listed: {alerts_count_before} -> {alerts_count_after}")
    print(f"[INFO] DB speeding events 10min: {db_events}")
    print(f"[INFO] DB alerts 10min: {db_alerts}")

    phase2_ok = (
        delta_fp >= 20
        and cams1.get(CAM108, {}).get("last_error") is None
        and cams1.get(CAM108, {}).get("running") is True
    )
    print("[OK] Phase 2 ingest stable" if phase2_ok else "[WARN] Phase 2 ingest weak or unstable")

    out = {
        "phase1_ok": phase1_ok,
        "phase2_ok": phase2_ok,
        "delta_frames_processed_5min": delta_fp,
        "delta_frames_dropped_5min": delta_fd,
        "db_speeding_10min": db_events,
        "db_alerts_10min": db_alerts,
        "rule_row": rule_row,
        "speed_zones": speed_zones,
    }
    out_path = ROOT / "scripts" / "_live_test_phase12_report.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[REPORT] {out_path}")
    return 0 if phase1_ok and phase2_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
