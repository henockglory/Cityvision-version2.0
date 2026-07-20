#!/usr/bin/env python3
"""Validation ciblée feu rouge — 1 alerte Frigate avec bbox cohérente."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
RULE_NAME = "Démo · Feu rouge"
EVENT_TYPE = "red_light_violation"
MAX_WAIT_SEC = int(os.environ.get("RULE_DURATION_SEC", "600"))
POLL_SEC = int(os.environ.get("POLL_SEC", "15"))
MAX_ALIGN_MS = int(os.environ.get("FRIGATE_MAX_ALIGN_MS", "20000"))


def req(method: str, url: str, token: str | None = None, body: dict | None = None, internal: bool = False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal:
        headers["X-Internal-Key"] = INTERNAL
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip()


def ai_health() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=5) as r:
            return json.loads(r.read()).get("status") == "ok"
    except Exception:
        return False


def camera_status(cam_id: str) -> dict:
    if not ai_health():
        return {"last_error": "ai_down"}
    try:
        data = req("GET", "http://127.0.0.1:8001/cameras")
        for c in data.get("cameras", []):
            if c.get("camera_id") == cam_id:
                return c
    except Exception as exc:
        return {"last_error": str(exc)}
    return {"last_error": "camera_not_registered"}


def wait_frigate_events(frigate_cam: str, sec: int = 90) -> int:
    base = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
    qs = urllib.parse.urlencode({"cameras": frigate_cam, "limit": 5})
    url = f"{base}/api/events?{qs}"
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                events = json.loads(resp.read().decode())
            n = len(events) if isinstance(events, list) else 0
            print(f"  frigate events={n} cam={frigate_cam[:20]}", flush=True)
            if n >= 1:
                return n
        except Exception as exc:
            print(f"  frigate poll err={exc}", flush=True)
        time.sleep(8)
    return 0


def wait_ingest(cam_id: str, sec: int = 120) -> dict:
    deadline = time.time() + sec
    last: dict = {}
    while time.time() < deadline:
        if not ai_health():
            print("  AI down — waiting", flush=True)
            time.sleep(5)
            continue
        last = camera_status(cam_id)
        fp = int(last.get("frames_processed") or 0)
        print(f"  ingest processed={fp} read={last.get('frames_read')} err={last.get('last_error')}", flush=True)
        if fp >= 6:
            return last
        try:
            req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
        except Exception:
            pass
        time.sleep(10)
    return last


def rule_camera_id(rule: dict) -> str:
    defn = rule.get("definition") or {}
    if isinstance(defn, str):
        defn = json.loads(defn)
    cam = defn.get("camera_id")
    if cam:
        return str(cam)
    bindings = defn.get("bindings") or {}
    return str(bindings.get("camera_id") or "")


def resolve_demo_video(token: str, cam_id: str) -> str | None:
    cams = req("GET", f"{API}/api/v1/orgs/{ORG}/cameras", token)
    for c in cams if isinstance(cams, list) else cams.get("cameras", []):
        if str(c.get("id")) == cam_id:
            meta = c.get("metadata") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            vid = meta.get("demo_video_id")
            return str(vid) if vid else None
    return None


def count_since(rule_id: str, since: str) -> tuple[int, int, int]:
    evt = psql(
        f"SELECT count(*) FROM events e JOIN cameras c ON c.id=e.camera_id "
        f"WHERE c.org_id='{ORG}'::uuid AND e.event_type='{EVENT_TYPE}' "
        f"AND e.ingested_at>='{since}'::timestamptz;"
    )
    alerts = psql(
        f"SELECT count(*) FROM alerts a WHERE a.org_id='{ORG}'::uuid "
        f"AND a.rule_id='{rule_id}'::uuid AND a.created_at>='{since}'::timestamptz;"
    )
    frigate = psql(
        f"SELECT count(*) FROM alerts a WHERE a.org_id='{ORG}'::uuid "
        f"AND a.rule_id='{rule_id}'::uuid AND a.created_at>='{since}'::timestamptz "
        f"AND a.evidence_snapshot->'package'->'metadata'->>'capture_source'='frigate_track';"
    )
    return int(evt or 0), int(alerts or 0), int(frigate or 0)


def print_bbox_audit(rule_id: str, since: str) -> tuple[bool, str]:
    row = psql(
        f"SELECT a.evidence_snapshot->'package'->'metadata'->>'bbox_source', "
        f"a.evidence_snapshot->'package'->'metadata'->'bbox', "
        f"a.evidence_snapshot->'package'->'metadata'->'ia_bbox', "
        f"a.evidence_snapshot->'package'->'metadata'->>'align_delta_ms', "
        f"a.evidence_snapshot->'package'->'metadata'->>'frigate_event_id' "
        f"FROM alerts a WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{rule_id}'::uuid "
        f"AND a.created_at>='{since}'::timestamptz "
        f"ORDER BY a.created_at DESC LIMIT 1;"
    )
    if not row or "|" not in row:
        print("  bbox audit: no alert evidence", flush=True)
        return False, "no evidence"
    parts = row.split("|", 4)
    print(f"  bbox_source={parts[0]}", flush=True)
    print(f"  frigate_bbox={parts[1]}", flush=True)
    print(f"  ia_bbox={parts[2]}", flush=True)
    print(f"  align_delta_ms={parts[3]} frigate_event={parts[4]}", flush=True)
    align_ok = True
    try:
        align_ms = abs(int(float(parts[3] or 0)))
        if align_ms > MAX_ALIGN_MS:
            align_ok = False
            print(f"  [FAIL] align_delta_ms={align_ms} > max={MAX_ALIGN_MS}", flush=True)
    except (TypeError, ValueError):
        align_ok = False
        print("  [FAIL] align_delta_ms missing or invalid", flush=True)
    bbox_ok = parts[0] == "frigate_mqtt" and parts[1] not in ("", "null", None)
    if not bbox_ok:
        print("  [FAIL] bbox_source or frigate bbox missing", flush=True)
    return align_ok and bbox_ok, parts[3] or "?"


def main() -> int:
    print("=== Validation feu rouge — 1 détection Frigate ===", flush=True)
    if not ai_health():
        print("[FAIL] AI not running — python3 scripts/_restart_ai.py", flush=True)
        return 1

    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    tok = login["access_token"]
    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
    feu = next((r for r in rules if r.get("name") == RULE_NAME), None)
    if not feu:
        print(f"[FAIL] rule missing: {RULE_NAME}", flush=True)
        return 1

    cam_id = rule_camera_id(feu)
    if not cam_id:
        print("[FAIL] feu rule has no camera_id", flush=True)
        return 1
    video_id = resolve_demo_video(tok, cam_id)
    if not video_id:
        print(f"[FAIL] no demo_video_id for camera {cam_id[:8]}", flush=True)
        return 1

    for r in rules:
        if str(r.get("name", "")).startswith("Démo"):
            req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}", tok, {"is_enabled": False})
    time.sleep(3)

    req("PATCH", f"{API}/api/v1/orgs/{ORG}/demo/settings", tok, {
        "source_mode": "video", "active_video_id": video_id, "active_camera_id": None,
    })
    print(f"feu video active cam={cam_id[:8]} vid={video_id[:8]}", flush=True)

    frigate_cam = f"cv_{cam_id}"
    if wait_frigate_events(frigate_cam, 90) < 1:
        print("[WARN] no Frigate events yet", flush=True)

    st = wait_ingest(cam_id, 120)
    if int(st.get("frames_processed") or 0) < 6:
        print("[FAIL] ingest not ready", flush=True)
        return 1

    since = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S%z").replace("+0000", "+00")
    req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{feu['id']}", tok, {"is_enabled": True})
    print(f"rule enabled — stop at 1 alert (max {MAX_WAIT_SEC}s)", flush=True)

    deadline = time.time() + MAX_WAIT_SEC
    while time.time() < deadline:
        time.sleep(POLL_SEC)
        evt, alerts, frigate = count_since(feu["id"], since)
        print(f"  poll events={evt} alerts={alerts} frigate_track={frigate}", flush=True)
        if alerts >= 1 and frigate >= 1:
            print("[HIT] 1 alert with frigate_track", flush=True)
            break
        if not ai_health():
            print("  WARN AI down", flush=True)

    evt, alerts, frigate = count_since(feu["id"], since)
    req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{feu['id']}", tok, {"is_enabled": False})
    sync_ok, align_val = print_bbox_audit(feu["id"], since)

    print(f"FINAL events={evt} alerts={alerts} frigate_track={frigate}", flush=True)
    if alerts >= 1 and frigate >= 1 and sync_ok:
        status = "PASS"
    elif alerts >= 1 and frigate >= 1:
        status = "PARTIAL"
        print(f"[PARTIAL] frigate_track ok but sync check failed (align={align_val})", flush=True)
    elif evt >= 1:
        status = "PARTIAL"
    else:
        status = "FAIL"
    print(f"RESULT: {status}", flush=True)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
