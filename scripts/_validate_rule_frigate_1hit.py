#!/usr/bin/env python3
"""Validation ciblée — 1 alerte Frigate pour une règle démo (env RULE_NAME)."""
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
MAX_WAIT_SEC = int(os.environ.get("RULE_DURATION_SEC", "600"))
POLL_SEC = int(os.environ.get("POLL_SEC", "15"))
MAX_ALIGN_MS = int(os.environ.get("FRIGATE_MAX_ALIGN_MS", "30000"))
SETTLE_SEC = int(os.environ.get("DEMO_SETTLE_SEC", "10"))

RULE_EVENT_TYPES: dict[str, list[str]] = {
    "Démo · Excès de vitesse": ["speeding"],
    "Démo · Téléphone au volant": ["phone_use_violation", "phone_driving", "driver_phone"],
    "Démo · Feu rouge": ["red_light_violation"],
    "Démo · Ceinture": ["seatbelt_violation", "seatbelt"],
    "Démo · Non-port ceinture": ["seatbelt_violation", "seatbelt"],
    "Démo · Comptage": ["line_cross", "vehicle_count_threshold", "vehicle_corridor", "zone_count"],
    "Démo · Comptage véhicules": ["line_cross", "vehicle_count_threshold", "vehicle_corridor", "zone_count"],
}


def req(method: str, url: str, token: str | None = None, body: dict | None = None, internal: bool = False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal:
        headers["X-Internal-Key"] = INTERNAL
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=180) as resp:
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
            d = json.loads(r.read())
            return d.get("status") == "ok" and str(d.get("models_all_ok", "")).lower() == "true"
    except Exception:
        return False


def backend_health() -> bool:
    try:
        with urllib.request.urlopen(f"{API}/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def camera_status(cam_id: str) -> dict:
    try:
        data = req("GET", "http://127.0.0.1:8001/cameras")
        for c in data.get("cameras", []):
            if c.get("camera_id") == cam_id:
                return c
    except Exception as exc:
        return {"last_error": str(exc)}
    return {"last_error": "camera_not_registered"}


def wait_frigate_fresh(frigate_cam: str, max_age_sec: float = 25.0, sec: int = 180) -> bool:
    """Wait until Frigate emits an event younger than max_age_sec (live sync).

    Also accepts live detect: camera_fps>0 and detection_fps>0 when /api/events
    only has long-lived tracks (start_time stays old on looping demos).
    """
    try:
        max_age_sec = float(os.environ.get("FRIGATE_FRESH_MAX_AGE_SEC", max_age_sec))
    except (TypeError, ValueError):
        pass
    base = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
    qs = urllib.parse.urlencode({"cameras": frigate_cam, "limit": 10})
    url = f"{base}/api/events?{qs}"
    stats_url = f"{base}/api/stats"
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                events = json.loads(resp.read().decode())
            now = time.time()
            if isinstance(events, list):
                for ev in events:
                    st = ev.get("start_time")
                    et = ev.get("end_time")
                    # Fresh start OR recently ended OR still in-progress with recent path update
                    if isinstance(st, (int, float)) and (now - float(st)) <= max_age_sec:
                        age = now - float(st)
                        print(
                            f"  frigate FRESH age={age:.1f}s id={str(ev.get('id',''))[:20]} "
                            f"cam={frigate_cam[:20]}",
                            flush=True,
                        )
                        return True
                    if isinstance(et, (int, float)) and (now - float(et)) <= max_age_sec:
                        print(
                            f"  frigate FRESH end_age={now-float(et):.1f}s id={str(ev.get('id',''))[:20]} "
                            f"cam={frigate_cam[:20]}",
                            flush=True,
                        )
                        return True
                n = len(events)
                if n:
                    st0 = events[0].get("start_time")
                    age0 = (now - float(st0)) if isinstance(st0, (int, float)) else -1
                    print(f"  frigate events={n} youngest_age={age0:.0f}s (need <={max_age_sec}s)", flush=True)
                else:
                    print(f"  frigate events=0 for {frigate_cam[:24]}", flush=True)
            # Live detect fallback (looping demos keep long-lived start_time)
            with urllib.request.urlopen(stats_url, timeout=8) as resp:
                stats = json.loads(resp.read().decode())
            cam_stats = (stats.get("cameras") or {}).get(frigate_cam) or {}
            fps = float(cam_stats.get("camera_fps") or 0)
            det = float(cam_stats.get("detection_fps") or 0)
            if fps >= 1.0 and det >= 0.5:
                print(
                    f"  frigate LIVE detect fps={fps:.1f} det={det:.1f} cam={frigate_cam[:20]}",
                    flush=True,
                )
                return True
        except Exception as exc:
            print(f"  frigate poll err={exc}", flush=True)
        time.sleep(8)
    return False


def repair_demo_streams() -> None:
    try:
        out = req("POST", f"{API}/api/v1/internal/demo/repair-streams", internal=True)
        print(f"  repair-streams: {out}", flush=True)
    except Exception as exc:
        print(f"  WARN repair-streams: {exc}", flush=True)


def heal_frigate_if_stale(frigate_cam: str, max_age_sec: float = 30.0) -> bool:
    """Wait for live Frigate events; restart go2rtc+Frigate once if stale."""
    if wait_frigate_fresh(frigate_cam, max_age_sec=max_age_sec, sec=90):
        return True
    print("  frigate stale — repair streams + restart go2rtc+frigate", flush=True)
    repair_demo_streams()
    subprocess.run(
        ["docker", "restart", "citevision-v2-go2rtc", "citevision-v2-frigate"],
        capture_output=True, check=False,
    )
    time.sleep(25)
    # go2rtc loses in-memory streams on restart — re-register demo loops.
    repair_demo_streams()
    try:
        req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
    except Exception:
        pass
    time.sleep(15)
    return wait_frigate_fresh(frigate_cam, max_age_sec=max_age_sec, sec=180)


def wait_ingest(cam_id: str, sec: int = 120) -> dict:
    deadline = time.time() + sec
    last: dict = {}
    while time.time() < deadline:
        last = camera_status(cam_id)
        fp = int(last.get("frames_processed") or 0)
        print(f"  ingest processed={fp} err={last.get('last_error')}", flush=True)
        if fp >= 3:
            return last
        try:
            req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
        except Exception:
            pass
        time.sleep(8)
    return last


def rule_camera_id(rule: dict) -> str:
    defn = rule.get("definition") or {}
    if isinstance(defn, str):
        defn = json.loads(defn)
    cam = defn.get("camera_id")
    if cam:
        return str(cam)
    return str((defn.get("bindings") or {}).get("camera_id") or "")


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


# Cabin rules intentionally skip Frigate (see EvidenceCaptureService._CABIN_EVENT_TYPES)
# and attach ring-buffer packages with capture_source=live. Road rules require frigate_track.
_CABIN_RULE_NAMES = frozenset({
    "Démo · Téléphone au volant",
    "Démo · Ceinture",
    "Démo · Non-port ceinture",
})

# Observation counting: counter actions only (no alert / no evidence package).
_OBSERVATION_RULE_NAMES = frozenset({
    "Démo · Comptage",
    "Démo · Comptage véhicules",
})


def _evidence_source_ok_sql(rule_name: str) -> str:
    """SQL fragment: alert has acceptable capture_source for this rule family."""
    if rule_name in _CABIN_RULE_NAMES:
        return (
            "(a.evidence_snapshot->'package'->'metadata'->>'capture_source' "
            "IN ('live','frigate_track','ring_buffer'))"
        )
    return (
        "(a.evidence_snapshot->'package'->'metadata'->>'capture_source'='frigate_track')"
    )


def line_counter_total(cam_id: str, line_name: str = "Ligne_count") -> int:
    row = psql(
        f"SELECT coalesce(sum(count_total),0) FROM line_counters "
        f"WHERE camera_id='{cam_id}'::uuid AND line_id='{line_name}';"
    )
    try:
        return int(row or 0)
    except ValueError:
        return 0


def count_since(rule_id: str, event_types: list[str], since: str, rule_name: str = "") -> tuple[int, int, int]:
    types_sql = ",".join(f"'{t}'" for t in event_types)
    evt = psql(
        f"SELECT count(*) FROM events e JOIN cameras c ON c.id=e.camera_id "
        f"WHERE c.org_id='{ORG}'::uuid AND e.event_type IN ({types_sql}) "
        f"AND e.ingested_at>='{since}'::timestamptz;"
    )
    alerts = psql(
        f"SELECT count(*) FROM alerts a WHERE a.org_id='{ORG}'::uuid "
        f"AND a.rule_id='{rule_id}'::uuid AND a.created_at>='{since}'::timestamptz;"
    )
    src_ok = _evidence_source_ok_sql(rule_name)
    frigate = psql(
        f"SELECT count(*) FROM alerts a WHERE a.org_id='{ORG}'::uuid "
        f"AND a.rule_id='{rule_id}'::uuid AND a.created_at>='{since}'::timestamptz "
        f"AND {src_ok};"
    )
    return int(evt or 0), int(alerts or 0), int(frigate or 0)


def print_bbox_audit(rule_id: str, since: str) -> tuple[bool, str]:
    row = psql(
        f"SELECT a.evidence_snapshot->'package'->'metadata'->>'bbox_source', "
        f"a.evidence_snapshot->'package'->'metadata'->'bbox', "
        f"a.evidence_snapshot->'package'->'metadata'->>'align_delta_ms', "
        f"a.evidence_snapshot->'package'->'metadata'->>'frigate_event_id' "
        f"FROM alerts a WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{rule_id}'::uuid "
        f"AND a.created_at>='{since}'::timestamptz ORDER BY a.created_at DESC LIMIT 1;"
    )
    if not row or "|" not in row:
        print("  bbox audit: no alert evidence", flush=True)
        return False, "no evidence"
    parts = row.split("|", 3)
    print(f"  bbox_source={parts[0]} frigate_bbox={parts[1]}", flush=True)
    print(f"  align_delta_ms={parts[2]} frigate_event={parts[3]}", flush=True)
    align_ok = True
    try:
        if abs(int(float(parts[2] or 0))) > MAX_ALIGN_MS:
            align_ok = False
            print(f"  [FAIL] align_delta_ms>{MAX_ALIGN_MS}", flush=True)
    except (TypeError, ValueError):
        align_ok = False
    bbox_ok = parts[0] == "frigate_mqtt" and parts[1] not in ("", "null")
    return align_ok and bbox_ok, parts[2] or "?"


def main() -> int:
    rule_name = os.environ.get("RULE_NAME", "").strip()
    if not rule_name:
        print("[FAIL] set RULE_NAME env", flush=True)
        return 1
    event_types = RULE_EVENT_TYPES.get(rule_name)
    if not event_types:
        raw = os.environ.get("EVENT_TYPES", "")
        event_types = [s.strip() for s in raw.split(",") if s.strip()]
    if not event_types:
        print(f"[FAIL] unknown rule event types for {rule_name}", flush=True)
        return 1

    print(f"=== Validation 1 hit — {rule_name} ===", flush=True)
    if not ai_health():
        print("[FAIL] AI not healthy — bash scripts/_restart_ai_cuda.sh", flush=True)
        return 1
    if not backend_health():
        print("[FAIL] backend down — bash scripts/_restart_backend.sh", flush=True)
        return 1
    try:
        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as r:
            if r.status != 200:
                raise OSError("rules-engine down")
    except Exception:
        print("[FAIL] rules-engine down — bash scripts/_start-rules-engine.sh", flush=True)
        return 1

    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    tok = login["access_token"]
    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
    rule = next((r for r in rules if r.get("name") == rule_name), None)
    if not rule:
        print(f"[FAIL] rule missing: {rule_name}", flush=True)
        return 1

    cam_id = rule_camera_id(rule)
    video_id = resolve_demo_video(tok, cam_id) if cam_id else None
    if not cam_id or not video_id:
        print(f"[FAIL] cam/video missing cam={cam_id} vid={video_id}", flush=True)
        return 1

    # Disable other demo rules only. Keep the target rule enabled BEFORE Frigate
    # rebuild so CompileEvidenceAggregate turns record+snapshots on (otherwise
    # Frigate stops emitting clip events and heal_frigate_if_stale never passes).
    # skip_preflight=1: DEMO_MODE waits on ingest preflight and returns 409 when
    # no camera is active yet (video switch happens just below).
    for r in rules:
        name = str(r.get("name", ""))
        if not name.startswith("Démo"):
            continue
        want = name == rule_name
        req(
            "PATCH",
            f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}?skip_preflight=1",
            tok,
            {"is_enabled": want},
        )
    time.sleep(3)

    demo_st = req("PATCH", f"{API}/api/v1/orgs/{ORG}/demo/settings", tok, {
        "source_mode": "video", "active_video_id": video_id, "active_camera_id": None,
    })
    print(
        f"video active cam={cam_id[:8]} vid={video_id[:8]} "
        f"pipeline={demo_st.get('pipeline_status')} ingest={demo_st.get('ingest_ready')}",
        flush=True,
    )
    if not demo_st.get("ingest_ready"):
        if demo_st.get("pipeline_status") == "degraded":
            print("[FAIL] demo pipeline degraded after switch", flush=True)
            return 1
        print("  waiting ingest (fallback)...", flush=True)
        st = wait_ingest(cam_id, 90)
        if int(st.get("frames_processed") or 0) < 3:
            print("[FAIL] ingest not ready after video switch", flush=True)
            return 1

    frigate_cam = f"cv_{cam_id}"
    repair_demo_streams()
    observation = rule_name in _OBSERVATION_RULE_NAMES
    if observation:
        print("  observation rule — skip Frigate freshness/rebuild gate", flush=True)
    elif os.environ.get("SKIP_FRIGATE_REBUILD", "").strip() in ("1", "true", "yes"):
        print("  SKIP_FRIGATE_REBUILD — keep current Frigate config/media", flush=True)
    else:
        # Soft rebuild only: backend skips Frigate reload when YAML unchanged
        # (permanent demo record+snapshots). Never docker-restart Frigate here —
        # that caused HTTP 502 storms during 1-hit validation.
        try:
            req("POST", f"{API}/api/v1/internal/ingest/frigate/rebuild", internal=True)
            print("  frigate rebuild requested (no-op if config unchanged)", flush=True)
        except Exception as exc:
            print(f"  WARN frigate rebuild: {exc}", flush=True)
    if not observation:
        repair_demo_streams()
        if not heal_frigate_if_stale(frigate_cam, max_age_sec=25.0):
            print("[FAIL] Frigate not fresh for demo camera — run _fix_frigate_fresh.sh", flush=True)
            return 1
    try:
        with urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:8010/internal/sync-rules", method="POST"),
            timeout=10,
        ):
            pass
        print("  rules-engine synced", flush=True)
    except Exception as exc:
        print(f"  WARN rules sync: {exc}", flush=True)
    if SETTLE_SEC > 0:
        print(f"  settle {SETTLE_SEC}s after switch...", flush=True)
        time.sleep(SETTLE_SEC)

    since = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S%z").replace("+0000", "+00")
    # Target rule already enabled above (needed for Frigate record aggregate).
    if observation:
        print(f"observation enabled — stop at 1 line_cross / counter bump (max {MAX_WAIT_SEC}s)", flush=True)
        ctr0 = line_counter_total(cam_id)
        deadline = time.time() + MAX_WAIT_SEC
        evt = alerts = evidence_ok = 0
        while time.time() < deadline:
            time.sleep(POLL_SEC)
            evt, alerts, evidence_ok = count_since(rule["id"], event_types, since, rule_name)
            ctr = line_counter_total(cam_id)
            delta = max(0, ctr - ctr0)
            print(
                f"  poll events={evt} alerts={alerts} counter_delta={delta} (base={ctr0})",
                flush=True,
            )
            if evt >= 1 or delta >= 1:
                print("[HIT] observation line_cross / counter", flush=True)
                break
            if not ai_health():
                print("  WARN AI unhealthy", flush=True)
        evt, alerts, evidence_ok = count_since(rule["id"], event_types, since, rule_name)
        ctr = line_counter_total(cam_id)
        delta = max(0, ctr - ctr0)
        req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{rule['id']}", tok, {"is_enabled": False})
        print(f"FINAL events={evt} alerts={alerts} counter_delta={delta}", flush=True)
        status = "PASS" if (evt >= 1 or delta >= 1) else "FAIL"
        print(f"RESULT: {rule_name}: {status}", flush=True)
        return 0 if status == "PASS" else 1

    print(f"rule enabled — stop at 1 alert+frigate (max {MAX_WAIT_SEC}s)", flush=True)

    deadline = time.time() + MAX_WAIT_SEC
    while time.time() < deadline:
        time.sleep(POLL_SEC)
        evt, alerts, evidence_ok = count_since(rule["id"], event_types, since, rule_name)
        label = "evidence_ok" if rule_name in _CABIN_RULE_NAMES else "frigate_track"
        print(f"  poll events={evt} alerts={alerts} {label}={evidence_ok}", flush=True)
        if alerts >= 1 and evidence_ok >= 1:
            print(f"[HIT] 1 alert with {label}", flush=True)
            break
        if not ai_health():
            print("  WARN AI unhealthy", flush=True)

    evt, alerts, evidence_ok = count_since(rule["id"], event_types, since, rule_name)
    req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{rule['id']}", tok, {"is_enabled": False})
    sync_ok, align_val = print_bbox_audit(rule["id"], since)
    cabin = rule_name in _CABIN_RULE_NAMES
    # Cabin live packages: bbox_source may not be frigate_mqtt — sync check is road-only.
    if cabin:
        sync_ok = True

    label = "evidence_ok" if cabin else "frigate_track"
    print(f"FINAL events={evt} alerts={alerts} {label}={evidence_ok}", flush=True)
    if alerts >= 1 and evidence_ok >= 1 and sync_ok:
        status = "PASS"
    elif alerts >= 1 and evidence_ok >= 1:
        status = "PARTIAL"
        print(f"[PARTIAL] sync check failed align={align_val}", flush=True)
    elif evt >= 1:
        status = "PARTIAL"
        print("[PARTIAL] events but no acceptable evidence alert — check suppress/capture", flush=True)
    else:
        status = "FAIL"
    print(f"RESULT: {rule_name}: {status}", flush=True)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
