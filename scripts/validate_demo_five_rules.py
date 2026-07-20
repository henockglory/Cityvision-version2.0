#!/usr/bin/env python3
"""E2E validation: N detections per demo rule (sequential), then disable all rules."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
API = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
MAILHOG = os.environ.get("MAILHOG_PUBLIC_URL", "http://localhost:8025")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")
TARGET = int(os.environ.get("TARGET_DETECTIONS", "2"))
TIMEOUT = int(os.environ.get("RULE_TIMEOUT_SEC", "600"))
SYNC_WAIT = int(os.environ.get("RULE_SYNC_WAIT_SEC", "35"))
# [P.131] No hardcoded IDs. Org is resolved live from /auth/me; an explicit
# DEMO_ORG_ID env override is honored only when the operator sets it on purpose.
DEMO_ORG = os.environ.get("DEMO_ORG_ID", "")
# Comma-separated rule names to validate (default: all). Example:
# VALIDATE_ONLY="Démo · Feu rouge,Démo · Excès de vitesse"
VALIDATE_ONLY = [
    s.strip() for s in os.environ.get("VALIDATE_ONLY", "").split(",") if s.strip()
]

# Order: comptage → ceinture → vitesse → téléphone → feu rouge (one rule active at a time).
RULES = [
    {
        "name": "Démo · Comptage véhicules",
        "event_types": ["line_cross"],
        "mail": False,
        "counter": True,
        # [P.131] camera_id resolved live (see resolve_counter_camera) — never hardcoded.
        "camera_id": None,
        "counter_camera_hint": "compt",
        "require_alert": False,
    },
    {"name": "Démo · Non-port ceinture", "event_types": ["seatbelt_violation"], "mail": True, "counter": False},
    {"name": "Démo · Excès de vitesse", "event_types": ["speeding"], "mail": True, "counter": False},
    {"name": "Démo · Téléphone au volant", "event_types": ["phone_use_violation"], "mail": True, "counter": False},
    {"name": "Démo · Feu rouge", "event_types": ["red_light_violation"], "mail": True, "counter": False},
]


def _results_to_rules_map(results: list[dict]) -> dict[str, dict]:
    """Normalize validate_demo results for ROADMAP-138 tracker."""
    key_map = {
        "Démo · Comptage véhicules": "line_count",
        "Démo · Non-port ceinture": "seatbelt",
        "Démo · Excès de vitesse": "speed",
        "Démo · Téléphone au volant": "phone",
        "Démo · Feu rouge": "red_light",
    }
    out: dict[str, dict] = {}
    for r in results:
        key = key_map.get(str(r.get("rule", "")))
        if not key:
            continue
        st = str(r.get("status", "")).lower()
        out[key] = {
            "status": "pass" if st == "pass" else ("deferred" if st == "skipped" else "fail"),
            "detail": r.get("detail", ""),
            "new_count": r.get("new_count", 0),
        }
    return out


def req(method: str, url: str, token: str | None = None, body: dict | None = None, timeout: int = 120) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def login_token() -> str:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    return login["access_token"]


def mail_count() -> int:
    try:
        with urllib.request.urlopen(f"{MAILHOG}/api/v2/messages?limit=1", timeout=5) as resp:
            return int(json.loads(resp.read()).get("total", 0))
    except Exception:
        return 0


def health_gate() -> None:
    req("GET", f"{API}/health")
    ai = req("GET", f"http://localhost:{os.environ.get('AI_ENGINE_PORT', '8001')}/health")
    for k in ("yolo_loaded", "face_loaded", "plate_loaded"):
        if str(ai.get(k, "")).lower() != "true":
            raise SystemExit(f"AI health: {k} not true")
    for k in ("driver_phone_model_loaded", "seatbelt_model_loaded"):
        if str(ai.get(k, "")).lower() != "true":
            raise SystemExit(f"AI secondary model not loaded: {k}")
    re = req("GET", f"http://localhost:{os.environ.get('RULES_ENGINE_PORT', '8010')}/health")
    print(f"rules-engine: {re}")


def _payload(e: dict) -> dict:
    payload = e.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    return payload


def count_demo_events(
    token: str,
    org: str,
    event_types: list[str],
    since_iso: str | None = None,
) -> int:
    """Count demo events of the given types.

    When *since_iso* is an ISO timestamp, only events that occurred AFTER
    that timestamp are counted.  This avoids the limit=100 API cap bug: if
    the camera generates hundreds of events between tests the baseline already
    saturates at 100, making evt_now - evt_baseline = 0.  Counting strictly
    after *since_iso* works because at most ~10 events are generated per
    35-second test window, so the 100-event window always covers them.
    """
    n = 0
    for et in event_types:
        try:
            rows = req(
                "GET",
                f"{API}/api/v1/orgs/{org}/events?limit=100&event_type={et}",
                token,
            )
        except Exception:
            continue
        if not isinstance(rows, list):
            rows = rows.get("items", []) if isinstance(rows, dict) else []
        for e in rows:
            payload = _payload(e)
            is_demo = payload.get("demo") is True or (payload.get("metadata") or {}).get("demo") is True
            if not is_demo:
                continue
            if since_iso:
                # Events are returned newest-first; stop counting once we pass the baseline.
                ts = e.get("occurred_at") or e.get("ingested_at") or ""
                if ts and ts <= since_iso:
                    break
            n += 1
    return n


def _alert_meta(a: dict) -> dict:
    m = a.get("metadata") or {}
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except json.JSONDecodeError:
            m = {}
    return m


def list_demo_alert_ids(token: str, org: str) -> set[str]:
    rows = req("GET", f"{API}/api/v1/orgs/{org}/alerts?limit=200&include_incomplete=true", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    ids: set[str] = set()
    for a in rows:
        meta = _alert_meta(a)
        if meta.get("demo") is True or str(meta.get("demo", "")).lower() == "true":
            aid = a.get("id")
            if aid:
                ids.add(str(aid))
    return ids


def latest_demo_alert(token: str, org: str, baseline_ids: set[str]) -> dict | None:
    rows = req("GET", f"{API}/api/v1/orgs/{org}/alerts?limit=50&include_incomplete=true", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    for a in rows:
        aid = str(a.get("id", ""))
        if aid and aid not in baseline_ids:
            meta = _alert_meta(a)
            if meta.get("demo") is True or str(meta.get("demo", "")).lower() == "true":
                return a
    return None


def alert_evidence_ok(alert: dict, *, require_plate: bool = True) -> tuple[bool, str]:
    """Check demo evidence completeness: clip + scene + subject (+ plate for road rules)."""
    meta = _alert_meta(alert)
    snap = meta.get("evidence_snapshot") or meta.get("evidence") or {}
    pkg = snap.get("package") if isinstance(snap.get("package"), dict) else snap
    if not isinstance(pkg, dict):
        return False, "no_evidence_package"
    clip = pkg.get("clip") or {}
    if not (clip.get("url") or clip.get("asset_id")):
        return False, "missing_clip"
    images = pkg.get("images") or []
    roles = {str(i.get("role")) for i in images if isinstance(i, dict)}
    required = ["scene", "subject"]
    if require_plate:
        required.append("plate")
    missing = [r for r in required if r not in roles]
    if missing:
        return False, f"missing_images:{','.join(missing)}"
    return True, "complete"


def count_alerts(token: str, org: str) -> int:
    return len(list_demo_alert_ids(token, org))


def resolve_counter_camera(token: str, org: str, hint: str, rule: dict | None) -> str | None:
    """[P.131] Resolve the counting camera dynamically — no hardcoded UUID.

    Priority: (1) camera bound in the rule definition, (2) a camera whose name
    matches the hint (e.g. "compt"/"décompte"), (3) the only camera that has a
    line counter. Returns None if nothing can be resolved (caller degrades).
    """
    # (1) From the rule's own bindings, if present.
    if rule:
        definition = rule.get("definition")
        if isinstance(definition, str):
            try:
                definition = json.loads(definition)
            except json.JSONDecodeError:
                definition = {}
        bindings = (definition or {}).get("bindings") or {}
        cam = bindings.get("camera_id")
        if cam:
            return str(cam)

    # (2) By camera name hint.
    try:
        cams = req("GET", f"{API}/api/v1/orgs/{org}/cameras", token)
        if isinstance(cams, dict):
            cams = cams.get("items", [])
        if isinstance(cams, list):
            for c in cams:
                name = str(c.get("name", "")).lower()
                if hint and hint.lower() in name:
                    return str(c.get("id") or c.get("camera_id"))
    except Exception:
        pass

    # (3) The camera that already owns a line counter.
    try:
        rows = req("GET", f"{API}/api/v1/orgs/{org}/lines/counters", token)
        if isinstance(rows, list):
            for r in rows:
                cam = r.get("camera_id")
                if cam:
                    return str(cam)
    except Exception:
        pass
    return None


def count_observation_counter(token: str, org: str, camera_id: str) -> int:
    try:
        rows = req("GET", f"{API}/api/v1/orgs/{org}/observations/counters?camera_id={camera_id}", token)
    except Exception:
        return 0
    if not isinstance(rows, list):
        return 0
    return sum(int(r.get("count", 0)) for r in rows)


def count_line_counter(token: str, org: str, camera_id: str) -> int:
    try:
        rows = req("GET", f"{API}/api/v1/orgs/{org}/lines/counters?camera_id={camera_id}", token)
    except Exception:
        return 0
    if not isinstance(rows, list):
        return 0
    return max((int(r.get("count_total", 0)) for r in rows), default=0)


def set_rule(token: str, org: str, rule_id: str, enabled: bool) -> None:
    """Enable/disable a rule. Harness already ran ensure_rule_test_ready — skip
    backend wait_preflight to avoid 409 on Frigate 'degraded' (stale events)."""
    url = f"{API}/api/v1/orgs/{org}/rules/{rule_id}"
    if enabled:
        url += "?skip_preflight=1"
    try:
        req("PATCH", url, token, {"is_enabled": enabled}, timeout=180)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode()[:500]
        except Exception:
            pass
        if exc.code == 409 and enabled:
            # Retry once after a short wait (ingest may still be healing).
            print(f"  [warn] rule enable 409: {body}", flush=True)
            time.sleep(8)
            req(
                "PATCH",
                f"{API}/api/v1/orgs/{org}/rules/{rule_id}?skip_preflight=1",
                token,
                {"is_enabled": True},
                timeout=180,
            )
            return
        raise


def rule_camera_id(rule: dict | None) -> str | None:
    """Extract the camera_id a demo rule is bound to (definition.bindings.camera_id)."""
    if not rule:
        return None
    definition = rule.get("definition")
    if isinstance(definition, str):
        try:
            definition = json.loads(definition)
        except json.JSONDecodeError:
            definition = {}
    bindings = (definition or {}).get("bindings") or {}
    cam = bindings.get("camera_id") or (definition or {}).get("camera_id")
    return str(cam) if cam else None


def get_active_demo_video(token: str, org: str) -> str | None:
    try:
        st = req("GET", f"{API}/api/v1/orgs/{org}/demo/settings", token)
    except Exception:
        return None
    vid = (st or {}).get("active_video_id") if isinstance(st, dict) else None
    return str(vid) if vid else None


def camera_video_id(token: str, org: str, camera_id: str) -> str | None:
    """Resolve the demo video id backing a demo camera (metadata.demo_video_id)."""
    try:
        cams = req("GET", f"{API}/api/v1/orgs/{org}/cameras", token)
    except Exception:
        return None
    if isinstance(cams, dict):
        cams = cams.get("items", [])
    for c in cams or []:
        if str(c.get("id") or c.get("camera_id")) != str(camera_id):
            continue
        meta = c.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        vid = meta.get("demo_video_id")
        return str(vid) if vid else None
    return None


def set_active_demo_video(token: str, org: str, video_id: str) -> None:
    """[B.24]/[D.35] Demo ingestion is mono-camera and switched by ACTIVE VIDEO
    (the API rejects setting a demo/virtual camera via active_camera_id). Setting
    active_video_id makes the orchestrator resolve+start the backing camera with
    its behaviors automatically — no manual spatial push needed.
    """
    req(
        "PATCH",
        f"{API}/api/v1/orgs/{org}/demo/settings",
        token,
        {"source_mode": "video", "active_video_id": video_id},
        timeout=30,
    )


def kick_ai_camera(camera_id: str) -> None:
    """Stop one camera worker; orchestrator resync will restart it."""
    ai_port = os.environ.get("AI_ENGINE_PORT", "8001")
    try:
        req_obj = urllib.request.Request(
            f"http://localhost:{ai_port}/cameras/{camera_id}/stop",
            method="POST",
        )
        urllib.request.urlopen(req_obj, timeout=15)
        print(f"  [kick] stopped AI camera {camera_id[:8]}", flush=True)
    except Exception as exc:
        print(f"  [kick] stop warn: {exc}", flush=True)
    trigger_ingest_resync()
    time.sleep(12)


def wait_for_ai_health(timeout_sec: int = 120) -> bool:
    ai_port = os.environ.get("AI_ENGINE_PORT", "8001")
    url = f"http://localhost:{ai_port}/health"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ok, err = _http_ok(url, timeout=5)
        if ok:
            return True
        print(f"  [wait-ai] {err}", flush=True)
        time.sleep(2)
    return False


def camera_processed_frames(camera_id: str) -> int:
    ai_port = os.environ.get("AI_ENGINE_PORT", "8001")
    short = camera_id[:8] if camera_id else ""
    try:
        with urllib.request.urlopen(f"http://localhost:{ai_port}/cameras", timeout=8) as resp:
            body = json.loads(resp.read().decode())
        for cam in body.get("cameras") or []:
            cid = str(cam.get("camera_id") or "")
            if cid == camera_id or cid.startswith(short):
                return int(cam.get("frames_processed") or 0)
    except Exception:
        pass
    return 0


def heal_mono_camera_ingest(
    camera_id: str,
    rule_name: str = "",
    needs_phone_model: bool = False,
) -> None:
    """
    Reset ingest mono-caméra (Port de Ceinture / cabine).
    Stop workers + resync orchestrator ; restart IA seulement en dernier recours.
    """
    ai_port = os.environ.get("AI_ENGINE_PORT", "8001")
    print(f"  [heal-ingest] reset ingest mono-cam {camera_id[:8]}…", flush=True)
    try:
        with urllib.request.urlopen(f"http://localhost:{ai_port}/cameras", timeout=8) as resp:
            body = json.loads(resp.read().decode())
        for cam in body.get("cameras") or []:
            cid = str(cam.get("camera_id") or "")
            if not cid:
                continue
            try:
                req_obj = urllib.request.Request(
                    f"http://localhost:{ai_port}/cameras/{cid}/stop",
                    method="POST",
                )
                urllib.request.urlopen(req_obj, timeout=10)
            except Exception:
                pass
    except Exception as exc:
        print(f"  [heal-ingest] list cameras warn: {exc}", flush=True)

    _CABIN_BEHAVIORS = {"seatbelt", "phone_use", "driver_cabin"}

    def _get_camera_behaviors() -> set[str]:
        """Return behaviors configured on the target camera via /cameras/{cam}/spatial."""
        try:
            url = f"http://localhost:{ai_port}/cameras/{camera_id}/spatial"
            with urllib.request.urlopen(url, timeout=8) as resp:
                body = json.loads(resp.read().decode())
            return set(body.get("behaviors") or [])
        except Exception:
            pass
        return set()

    def _target_running_with_zones() -> bool:
        behaviors = _get_camera_behaviors()
        if not behaviors:
            return False
        # For cabin cameras, require at least one cabin behavior to be configured
        if needs_phone_model or "ceinture" in rule_name.lower():
            if not behaviors & _CABIN_BEHAVIORS:
                print(
                    f"  [heal-ingest] camera running but no cabin zones yet "
                    f"(behaviors={sorted(behaviors)}) — waiting…",
                    flush=True,
                )
                return False
        return True

    for attempt in range(8):
        trigger_ingest_resync()
        time.sleep(10)
        if _target_running_with_zones():
            behaviors = _get_camera_behaviors()
            print(
                f"  [heal-ingest] camera {camera_id[:8]} active with zones={sorted(behaviors)}",
                flush=True,
            )
            time.sleep(5)
            return
        print(f"  [heal-ingest] resync attempt {attempt + 1}: waiting for worker+zones", flush=True)

    root = os.environ.get("PROJECT_ROOT", str(ROOT))
    restart = Path(root) / "scripts" / "restart-ai-engine.sh"
    if restart.is_file():
        print("  [heal-ingest] last resort: restart AI engine", flush=True)
        try:
            subprocess.run(
                ["bash", str(restart)],
                cwd=str(root),
                timeout=200,
                check=False,
                capture_output=True,
            )
        except Exception as exc:
            print(f"  [heal-ingest] restart warn: {exc}", flush=True)
        if wait_for_ai_health(timeout_sec=120):
            for attempt in range(6):
                trigger_ingest_resync()
                time.sleep(12)
                if _target_running_with_zones():
                    print(f"  [heal-ingest] camera {camera_id[:8]} active post-restart", flush=True)
                    break
                print(f"  [heal-ingest] post-restart resync {attempt + 1}", flush=True)
    time.sleep(5)


def wait_ai_camera_frames(
    camera_id: str,
    min_frames: int = 20,
    timeout_sec: int = 120,
    *,
    allow_heal: bool = True,
) -> bool:
    """Poll AI engine until the target camera has processed enough frames."""
    ai_port = os.environ.get("AI_ENGINE_PORT", "8001")
    url = f"http://localhost:{ai_port}/cameras"
    deadline = time.time() + timeout_sec
    short = camera_id[:8] if camera_id else "?"
    last_processed = -1
    last_read = -1
    stall_polls = 0
    healed = False
    poll_n = 0
    empty_polls = 0

    while time.time() < deadline:
        poll_n += 1
        if poll_n % 7 == 0:
            stop_extra_ai_cameras(camera_id)
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                body = json.loads(resp.read().decode())
            cams = body.get("cameras") or []
            matched = [
                c for c in cams
                if str(c.get("camera_id") or "") == camera_id
                or str(c.get("camera_id") or "").startswith(short)
            ]
            if not matched:
                empty_polls += 1
                if empty_polls <= 5 or empty_polls % 10 == 0:
                    print(f"  ingest {short}: no AI worker (empty_poll={empty_polls})", flush=True)
                if empty_polls in (3, 8, 15, 30):
                    trigger_ingest_resync()
                time.sleep(3)
                continue
            empty_polls = 0
            for cam in matched:
                frames = int(cam.get("frames_processed") or 0)
                read = int(cam.get("frames_read") or 0)
                running = bool(cam.get("running"))
                err = cam.get("last_error")
                print(
                    f"  ingest {short}: running={running} processed={frames} read={read} err={err}",
                    flush=True,
                )
                if running and frames >= min_frames:
                    return True
                if (
                    allow_heal
                    and not healed
                    and read > 800
                    and frames < min_frames
                    and frames == last_processed
                    and read > last_read + 200
                ):
                    stall_polls += 1
                else:
                    stall_polls = 0
                last_processed = frames
                last_read = read
                if allow_heal and stall_polls >= 3:
                    print(
                        f"  [heal-ingest] backlog détecté processed={frames} read={read}",
                        flush=True,
                    )
                    heal_mono_camera_ingest(camera_id)  # generic stall heal
                    healed = True
                    stall_polls = 0
                    last_processed = -1
                    deadline = time.time() + max(60, timeout_sec // 2)
        except Exception as exc:
            print(f"  ingest poll warn: {exc}", flush=True)
        time.sleep(3)
    print(f"WARN: camera {short} did not reach {min_frames} frames in {timeout_sec}s")
    return False


def wait_demo_pipeline_ready(
    token: str,
    org: str,
    *,
    video_id: str | None = None,
    camera_id: str | None = None,
    timeout_sec: int = 120,
) -> bool:
    """Poll GET /demo/settings + AI frames until mono-camera demo pipeline is ready."""
    min_frames = int(os.environ.get("DEMO_MIN_FRAMES", "20"))
    deadline = time.time() + timeout_sec
    short = (camera_id or "?")[:8]
    while time.time() < deadline:
        if camera_id and wait_ai_camera_frames(camera_id, min_frames, timeout_sec=8):
            print(f"demo ingest ready via AI frames (cam {short})")
            return True
        try:
            st = req("GET", f"{API}/api/v1/orgs/{org}/demo/settings", token, timeout=15)
            active_vid = str(st.get("active_video_id") or "")
            pipe = str(st.get("pipeline_status") or "")
            ingest = bool(st.get("ingest_ready"))
            active_cam = st.get("active_camera_id")
            if video_id and active_vid and active_vid != video_id:
                print(f"  demo settings: waiting active_video {active_vid[:8]} -> {video_id[:8]}")
            elif pipe == "ready" and ingest:
                if camera_id and wait_ai_camera_frames(camera_id, min_frames, timeout_sec=25):
                    print(f"demo pipeline ready (cam {short}, video {active_vid[:8]})")
                    return True
                if not camera_id:
                    print(f"demo pipeline ready (video {active_vid[:8]})")
                    return True
            else:
                print(f"  demo pipeline: status={pipe} ingest_ready={ingest} cam={str(active_cam or '')[:8]}")
        except Exception as exc:
            print(f"  demo settings poll warn: {exc}")
        time.sleep(4)
    print(f"WARN: demo pipeline not ready after {timeout_sec}s (cam {short})")
    return False


def stop_extra_ai_cameras(keep_camera_id: str) -> None:
    """Stop non-scenario AI ingest workers so mono-camera demo gets GPU time."""
    ai_port = os.environ.get("AI_ENGINE_PORT", "8001")
    url = f"http://localhost:{ai_port}/cameras"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            body = json.loads(resp.read().decode())
        for cam in body.get("cameras") or []:
            cid = str(cam.get("camera_id") or "")
            if not cid or cid == keep_camera_id:
                continue
            stop_url = f"http://localhost:{ai_port}/cameras/{cid}/stop"
            req_obj = urllib.request.Request(stop_url, method="POST")
            urllib.request.urlopen(req_obj, timeout=10)
            print(f"  stopped extra AI camera {cid[:8]}")
    except Exception as exc:
        print(f"WARN: stop extra AI cameras: {exc}")


DOCKER_WSL_CONTAINERS = (
    "citevision-v2-postgres",
    "citevision-v2-redis",
    "citevision-v2-minio",
    "citevision-v2-mosquitto",
    "citevision-v2-go2rtc",
    "citevision-v2-frigate",
    "citevision-v2-mailhog",
)


def ensure_docker_infra_wsl() -> bool:
    """Docker natif WSL uniquement — jamais Docker Desktop."""
    print("  [infra] Docker WSL natif (pas Desktop)", flush=True)
    try:
        probe = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=20,
            check=False,
        )
        if probe.returncode != 0:
            err = (probe.stderr or probe.stdout or b"").decode(errors="replace")[:120]
            _pf_line("Docker daemon", False, err or "docker info failed")
            return False
        _pf_line("Docker daemon", True)
    except FileNotFoundError:
        _pf_line("Docker daemon", False, "docker CLI absent")
        return False
    except Exception as exc:
        _pf_line("Docker daemon", False, str(exc))
        return False

    all_ok = True
    for name in DOCKER_WSL_CONTAINERS:
        running = False
        detail = ""
        try:
            subprocess.run(
                ["docker", "start", name],
                capture_output=True,
                timeout=45,
                check=False,
            )
            insp = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            running = insp.stdout.strip() == "true"
            if not running:
                detail = (insp.stderr or insp.stdout or "").strip()[:80]
        except Exception as exc:
            detail = str(exc)
        _pf_line(f"Container {name}", running, detail)
        if not running:
            all_ok = False
    return all_ok


def verify_go2rtc_demo_stream(org: str, video_id: str) -> tuple[bool, str]:
    """Vérifie que le flux RTSP démo loopé existe et produit des bytes (lecture active)."""
    if not org or not video_id:
        return False, "org/video_id manquant"
    stream = f"demo-{org.split('-')[0]}-{video_id.split('-')[0]}"
    try:
        with urllib.request.urlopen("http://127.0.0.1:1984/api/streams", timeout=8) as resp:
            streams = json.loads(resp.read().decode())
        info = streams.get(stream) if isinstance(streams, dict) else None
        if not info:
            # fallback: any stream key containing video prefix
            vid8 = video_id.split("-")[0]
            for k, v in (streams or {}).items():
                if vid8 in k:
                    stream, info = k, v
                    break
        if not info:
            return False, f"stream {stream} absent"
        producers = info.get("producers") or []
        if not producers:
            return False, f"stream {stream} sans producer"
        return True, stream
    except Exception as exc:
        return False, str(exc)


def ensure_go2rtc_ready() -> bool:
    """go2rtc sert les flux RTSP démo loopés."""
    for url in (
        "http://127.0.0.1:1984/api",
        "http://127.0.0.1:8554/",
    ):
        ok, err = _http_ok(url, timeout=6)
        if ok:
            _pf_line("go2rtc (flux démo RTSP)", True, url)
            return True
    _pf_line("go2rtc (flux démo RTSP)", False, "1984/8554 unreachable")
    return False


def trigger_ingest_resync() -> None:
    key = os.environ.get("INTERNAL_API_KEY", "") or "changeme_internal_service_key"
    headers = {"X-Internal-Key": key, "Content-Type": "application/json"}
    for path in (
        "/api/v1/internal/ingest/resync-spatial",
        "/api/v1/internal/demo/repair-streams",
    ):
        try:
            req_obj = urllib.request.Request(
                f"{API}{path}", data=b"{}", headers=headers, method="POST",
            )
            with urllib.request.urlopen(req_obj, timeout=60) as resp:
                _ = resp.read()
            print(f"  [sync] POST {path}", flush=True)
        except Exception as exc:
            print(f"  [sync] POST {path} warn: {exc}", flush=True)


def _pf_line(step: str, ok: bool, detail: str = "") -> None:
    mark = "OK" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{mark}] {step}{suffix}", flush=True)


def _http_ok(url: str, timeout: int = 8) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status >= 400:
                return False, f"HTTP {resp.status}"
            return True, ""
    except Exception as exc:
        return False, str(exc)


def heal_platform_stack(token: str | None, org: str, *, force_rebuild: bool = False) -> None:
    """Best-effort heal: demo streams + optional Frigate config rebuild.

    Frigate rebuild is only attempted when ``force_rebuild=True`` (i.e. Frigate
    was already down). When Frigate is alive, a rebuild is disruptive (causes a
    30-60 s reload) and is therefore skipped in favour of a lighter repair-streams
    + spatial resync only.
    """
    key = os.environ.get("INTERNAL_API_KEY", "") or "changeme_internal_service_key"
    if not os.environ.get("INTERNAL_API_KEY"):
        print("  [WARN] INTERNAL_API_KEY unset — fallback changeme_internal_service_key", flush=True)
    headers = {"X-Internal-Key": key, "Content-Type": "application/json"}

    # Always repair streams.
    try:
        req_obj = urllib.request.Request(
            f"{API}/api/v1/internal/demo/repair-streams", data=b"{}", headers=headers, method="POST",
        )
        with urllib.request.urlopen(req_obj, timeout=30) as resp:
            body = resp.read().decode()[:120]
        print(f"  [heal] POST /api/v1/internal/demo/repair-streams -> {body}")
    except Exception as exc:
        print(f"  [heal] POST /api/v1/internal/demo/repair-streams warn: {exc}")

    # Frigate rebuild only when forced (Frigate was already dead).
    if force_rebuild:
        try:
            req_obj = urllib.request.Request(
                f"{API}/api/v1/internal/ingest/frigate/rebuild",
                data=b"{}", headers=headers, method="POST",
            )
            with urllib.request.urlopen(req_obj, timeout=60) as resp:
                body = resp.read().decode()[:120]
            print(f"  [heal] POST /api/v1/internal/ingest/frigate/rebuild -> {body}")
        except Exception as exc:
            print(f"  [heal] POST /api/v1/internal/ingest/frigate/rebuild warn: {exc}")
        # Restart Frigate container if API still down after rebuild attempt.
        frigate_url = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
        ok, _ = _http_ok(f"{frigate_url}/api/version", timeout=5)
        if not ok:
            try:
                subprocess.run(
                    ["docker", "restart", "citevision-v2-frigate"],
                    timeout=90, check=False, capture_output=True,
                )
                print("  [heal] docker restart citevision-v2-frigate", flush=True)
                for _ in range(15):
                    time.sleep(3)
                    ok, _ = _http_ok(f"{frigate_url}/api/version", timeout=5)
                    if ok:
                        break
            except Exception as exc:
                print(f"  [heal] frigate docker warn: {exc}", flush=True)


def frigate_camera_name(camera_id: str) -> str:
    return f"cv_{camera_id}"


def wait_frigate_events(camera_id: str, min_events: int = 1, timeout_sec: int = 90) -> bool:
    """Wait until Frigate has detection events for the demo camera (proof backend)."""
    frigate_url = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
    fid = frigate_camera_name(camera_id)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            qs = urllib.parse.urlencode({"cameras": fid, "limit": "5"})
            url = f"{frigate_url}/api/events?{qs}"
            with urllib.request.urlopen(url, timeout=12) as resp:
                rows = json.loads(resp.read().decode())
            n = len(rows) if isinstance(rows, list) else 0
            if n >= min_events:
                print(f"  frigate events OK on {fid[:28]} (n={n})")
                return True
            print(f"  frigate waiting events on {fid[:28]} (n={n})")
        except Exception as exc:
            print(f"  frigate poll warn: {exc}")
        time.sleep(5)
    print(f"WARN: frigate has <{min_events} events on {fid[:28]} after {timeout_sec}s")
    return False


def ensure_rule_test_ready(
    token: str,
    org: str,
    rule_name: str,
    *,
    camera_id: str | None,
    video_id: str | None,
    needs_frigate: bool = True,
    needs_phone_model: bool = False,
) -> tuple[bool, str]:
    """
    Gate obligatoire avant chaque règle démo : tous les acteurs ON et sains.
    Retourne (ok, detail) — si not ok, le test ne doit pas être interprété comme échec métier.
    """
    strict = os.environ.get("RULE_PREFLIGHT_STRICT", "1") != "0"
    min_frames = int(os.environ.get("DEMO_MIN_FRAMES", "15"))
    if needs_phone_model or "ceinture" in rule_name.lower():
        # 30 frames minimum for cabin cameras: the orchestrator needs a few seconds
        # to push zone configs after the worker starts. With only 6 frames, zones
        # are often not yet configured and secondary model (seatbelt/phone) won't
        # fire. 30 frames (~6s at 5fps) gives the orchestrator time to push zones.
        min_frames = int(os.environ.get("DEMO_MIN_FRAMES_CABIN", "30"))
    ready_sec = int(os.environ.get("DEMO_READY_TIMEOUT_SEC", "180"))
    if needs_phone_model or "ceinture" in rule_name.lower():
        ready_sec = int(os.environ.get("DEMO_READY_TIMEOUT_SEC_CABIN", "420"))
    frigate_wait = int(os.environ.get("FRIGATE_EVENTS_WAIT_SEC", "120"))
    # Ring buffer warm-up: after ingest starts, wait at least this many seconds
    # so the ring buffer (RING_SECONDS=12) has enough frames for a fallback clip.
    ring_warmup_sec = int(os.environ.get("RING_WARMUP_SEC", "15"))
    failed: list[str] = []

    print(f"\n--- PREFLIGHT: {rule_name} ---", flush=True)

    # 0 — Evidence backend gate: pure EVIDENCE_BACKEND=frigate (without demo strict
    # cabin fallback) disables the ring buffer. Demo mode uses DEMO_EVIDENCE_BACKEND
    # =strict_frigate which keeps cabin ring-buffer fallback — that is expected.
    ev_backend = os.environ.get("EVIDENCE_BACKEND", "ring_buffer").strip().lower()
    demo_mode = os.environ.get("DEMO_MODE", "0").strip() == "1"
    demo_ev = os.environ.get("DEMO_EVIDENCE_BACKEND", "strict_frigate").strip().lower()
    if ev_backend == "frigate" and not (demo_mode and demo_ev in ("strict_frigate", "hybrid", "frigate")):
        print(
            "  [WARN] EVIDENCE_BACKEND=frigate without DEMO_MODE — ring buffer disabled. "
            "Prefer DEMO_MODE=1 + DEMO_EVIDENCE_BACKEND=strict_frigate for cabin fallback.",
            flush=True,
        )
        failed.append("evidence_backend_frigate_only")
    elif demo_mode:
        _pf_line(
            "Evidence backend (démo)",
            True,
            f"DEMO_MODE=1 DEMO_EVIDENCE_BACKEND={demo_ev}",
        )

    # 0b — Infra Docker WSL + go2rtc
    if not ensure_docker_infra_wsl():
        failed.append("docker_infra")
    if not ensure_go2rtc_ready():
        failed.append("go2rtc")

    # 1 — Backend
    ok, err = _http_ok(f"{API}/health")
    _pf_line("Backend /health", ok, err)
    if not ok:
        failed.append("backend_health")

    ok, err = _http_ok(f"{API}/health/ready")
    _pf_line("Backend /health/ready", ok, err)
    if not ok:
        failed.append("backend_ready")

    # 2 — AI engine
    ai_port = os.environ.get("AI_ENGINE_PORT", "8001")
    ai_url = f"http://localhost:{ai_port}/health"
    ai_ok = False
    ai_detail = ""
    try:
        with urllib.request.urlopen(ai_url, timeout=10) as resp:
            ai = json.loads(resp.read().decode())
        ai_ok = str(ai.get("yolo_loaded", "")).lower() == "true"
        ai_detail = f"yolo={ai.get('yolo_provider', '?')} cuda={ai.get('yolo_cuda', '?')}"
        if needs_phone_model and str(ai.get("driver_phone_model_loaded", "")).lower() != "true":
            ai_ok = False
            ai_detail += " phone_model=missing"
        if "ceinture" in rule_name.lower() and str(ai.get("seatbelt_model_loaded", "")).lower() != "true":
            ai_ok = False
            ai_detail += " seatbelt_model=missing"
    except Exception as exc:
        ai_detail = str(exc)
    _pf_line("AI engine (YOLO + modèles)", ai_ok, ai_detail)
    if not ai_ok:
        print("  [heal] AI engine down — restart…", flush=True)
        root = os.environ.get("PROJECT_ROOT", str(ROOT))
        restart = Path(root) / "scripts" / "restart-ai-engine.sh"
        if restart.is_file():
            try:
                subprocess.run(
                    ["bash", str(restart)], cwd=str(root), timeout=200, check=False,
                )
                if wait_for_ai_health(timeout_sec=120):
                    try:
                        with urllib.request.urlopen(ai_url, timeout=10) as resp:
                            ai = json.loads(resp.read().decode())
                        ai_ok = str(ai.get("yolo_loaded", "")).lower() == "true"
                        ai_detail = f"yolo={ai.get('yolo_provider', '?')} (restarted)"
                        if needs_phone_model and str(ai.get("driver_phone_model_loaded", "")).lower() != "true":
                            ai_ok = False
                        if "ceinture" in rule_name.lower() and str(ai.get("seatbelt_model_loaded", "")).lower() != "true":
                            ai_ok = False
                        _pf_line("AI engine après restart", ai_ok, ai_detail)
                    except Exception as exc:
                        ai_detail = str(exc)
            except Exception as exc:
                print(f"  [heal] AI restart warn: {exc}", flush=True)
    if not ai_ok:
        failed.append("ai_engine")

    # 3 — Rules-engine
    re_port = os.environ.get("RULES_ENGINE_PORT", "8010")
    re_ok, re_err = _http_ok(f"http://localhost:{re_port}/health")
    _pf_line("Rules-engine /health", re_ok, re_err)
    if not re_ok:
        failed.append("rules_engine")

    # 4 — Frigate (heal si besoin ; rebuild seulement si Frigate était vraiment down)
    frigate_url = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
    frigate_ok, frigate_err = _http_ok(f"{frigate_url}/api/version", timeout=12)
    frigate_was_down = needs_frigate and not frigate_ok
    if frigate_was_down:
        print("  [heal] Frigate API down — repair streams + full rebuild…", flush=True)
        heal_platform_stack(token, org, force_rebuild=True)
        for _ in range(15):
            time.sleep(3)
            frigate_ok, frigate_err = _http_ok(f"{frigate_url}/api/version", timeout=8)
            if frigate_ok:
                break
    _pf_line("Frigate API /api/version", frigate_ok, frigate_err)
    if needs_frigate and not frigate_ok:
        failed.append("frigate_api")

    # 5 — Vidéo démo active (switch si nécessaire)
    if not video_id or not camera_id:
        _pf_line("Vidéo démo résolue", False, "camera_id ou video_id manquant")
        failed.append("demo_video_missing")
    else:
        try:
            st = req("GET", f"{API}/api/v1/orgs/{org}/demo/settings", token, timeout=15)
            active_vid = str(st.get("active_video_id") or "")
            if active_vid != video_id:
                print(f"  [switch] active_video {active_vid[:8] or 'none'} -> {video_id[:8]}", flush=True)
                set_active_demo_video(token, org, video_id)
                time.sleep(4)
                st = req("GET", f"{API}/api/v1/orgs/{org}/demo/settings", token, timeout=15)
                active_vid = str(st.get("active_video_id") or "")
            vid_ok = active_vid == video_id
            _pf_line(
                "Vidéo démo active (lecture en cours)",
                vid_ok,
                f"video={active_vid[:8]} cam={str(st.get('active_camera_id') or '')[:8]}",
            )
            if not vid_ok:
                failed.append("demo_video_active")
            elif vid_ok:
                g2_ok, g2_detail = verify_go2rtc_demo_stream(org, video_id)
                _pf_line("go2rtc flux démo actif (lecture)", g2_ok, g2_detail)
                if not g2_ok:
                    failed.append("go2rtc_stream")
                # Post-switch: repair streams + spatial resync.
                # Do NOT rebuild Frigate here when it was already alive — a rebuild
                # triggers a 30-60 s reload that breaks the Frigate evidence pipeline.
                print("  [heal] post-switch: repair-streams + resync spatial", flush=True)
                heal_platform_stack(token, org, force_rebuild=False)
                trigger_ingest_resync()
                time.sleep(8)
        except Exception as exc:
            _pf_line("Vidéo démo active", False, str(exc))
            failed.append("demo_video_switch")

    # 6 — Mono-camera : arrêter les autres workers IA
    if camera_id:
        stop_extra_ai_cameras(camera_id)
        _pf_line("Caméras IA parasites stoppées", True, f"keep={camera_id[:8]}")
        # Cabine (ceinture/téléphone) : reset ingest seulement si frames insuffisantes.
        # Threshold uses min_frames (not a lower constant) to ensure zones are
        # already configured before we skip the reset.
        if needs_phone_model or "ceinture" in rule_name.lower():
            already = camera_processed_frames(camera_id)
            if already >= min_frames:
                print(
                    f"  [heal-ingest] skip reset — already {already} processed frames",
                    flush=True,
                )
            else:
                heal_mono_camera_ingest(camera_id, rule_name=rule_name, needs_phone_model=needs_phone_model)

    # 7 — Ingest IA : frames sur la caméra cible
    ingest_ok = False
    if camera_id:
        ingest_ok = wait_ai_camera_frames(camera_id, min_frames, timeout_sec=ready_sec)
        _pf_line(
            f"Ingest IA ≥{min_frames} frames",
            ingest_ok,
            f"cam={camera_id[:8]}",
        )
        if not ingest_ok:
            failed.append("ai_ingest_frames")
        elif needs_frigate and ring_warmup_sec > 0:
            # Ring buffer warm-up: evidence fallback (hybrid mode) builds a clip
            # from RING_SECONDS=12 of buffered frames. We pause briefly to ensure
            # the ring buffer has at least 12 s of material before the test starts.
            print(f"  [ring-warmup] {ring_warmup_sec}s buffer d'amorçage ring buffer…", flush=True)
            time.sleep(ring_warmup_sec)
    elif not camera_id:
        _pf_line("Ingest IA", False, "pas de camera_id")
        failed.append("ai_ingest_frames")

    # 8 — Frigate events sur la caméra cible
    if needs_frigate and camera_id:
        frigate_ev_ok = wait_frigate_events(camera_id, min_events=1, timeout_sec=frigate_wait)
        _pf_line("Frigate events frais (caméra cible)", frigate_ev_ok, frigate_camera_name(camera_id)[:28])
        if not frigate_ev_ok:
            failed.append("frigate_events")

    # 9 — Mailhog (si règle envoie mail)
    mail_ok, mail_err = _http_ok(f"{MAILHOG}/api/v2/messages?limit=1", timeout=5)
    _pf_line("Mailhog (SMTP capture)", mail_ok, mail_err if not mail_ok else "reachable")

    # Final stop of parasitic cameras — resync-spatial can restart them after heal-ingest.
    # We stop them again right before the settle so GPU/CPU is fully available.
    if camera_id:
        stop_extra_ai_cameras(camera_id)

    settle = int(os.environ.get("DEMO_SETTLE_SEC", "20"))
    # Cabin cameras need more settle time: the YOLO tracker needs ~30s of stable
    # person tracks before the heuristic/secondary model reliably fires events.
    if needs_phone_model or "ceinture" in rule_name.lower():
        settle = int(os.environ.get("DEMO_SETTLE_SEC_CABIN", str(max(settle, 45))))
    print(f"  [settle] {settle}s stabilisation pipeline…", flush=True)
    time.sleep(settle)

    if failed:
        detail = "preflight_blocked:" + ",".join(failed)
        print(f"--- PREFLIGHT BLOCKED ({len(failed)} gate(s)) — test non lancé ---\n", flush=True)
        if strict:
            return False, detail
        print("  [WARN] RULE_PREFLIGHT_STRICT=0 — on continue malgré preflight incomplet", flush=True)
        return True, detail

    print("--- PREFLIGHT OK — lancement détection ---\n", flush=True)
    return True, "preflight_ok"


def disable_all(token: str, org: str, rules: list[dict]) -> None:
    for r in rules:
        if str(r.get("name", "")).startswith("Démo"):
            set_rule(token, org, r["id"], False)


def wait_active_rules(n: int, sec: int = 120) -> None:
    url = f"http://localhost:{os.environ.get('RULES_ENGINE_PORT', '8010')}/health"
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                active = int(json.loads(resp.read()).get("active_rules", -1))
            if active == n:
                print(f"active_rules={active}")
                return
        except Exception:
            pass
        time.sleep(3)
    print(f"WARN: active_rules != {n} after {sec}s")


def refresh_feux_stream() -> None:
    script = ROOT / "scripts/push_ai_spatial_from_api.py"
    if not script.is_file():
        return
    print("==> refresh feux AI stream before feu rule")
    try:
        subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            timeout=120,
            check=False,
            env=os.environ.copy(),
        )
        time.sleep(12)
    except Exception as exc:
        print(f"WARN: feux refresh: {exc}")


def main() -> int:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    report_tag = os.environ.get("REPORT_TAG", "tuning" if VALIDATE_ONLY else "five-rules")
    if report_tag == "sequential":
        report_md = logs / "demo-five-rules-sequential-report.md"
        report_json = logs / "demo-five-rules-sequential-report.json"
    elif report_tag == "seatbelt-quick":
        report_md = logs / "seatbelt-quick-report.md"
        report_json = logs / "seatbelt-quick-report.json"
    elif report_tag == "phone-quick":
        report_md = logs / "phone-quick-report.md"
        report_json = logs / "phone-quick-report.json"
    elif report_tag == "speed-quick":
        report_md = logs / "speed-quick-report.md"
        report_json = logs / "speed-quick-report.json"
    elif report_tag == "speed-retest":
        report_md = logs / "demo-five-rules-speed-retest.md"
        report_json = logs / "demo-five-rules-speed-retest.json"
    elif report_tag == "final":
        report_md = logs / "demo-five-rules-final-report.md"
        report_json = logs / "demo-five-rules-final-report.json"
    elif VALIDATE_ONLY:
        report_md = logs / "demo-five-rules-tuning-report.md"
        report_json = logs / "demo-five-rules-tuning-report.json"
    else:
        report_md = logs / "demo-five-rules-report.md"
        report_json = logs / "demo-five-rules-report.json"

    health_gate()

    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    token_at = time.time()
    me = req("GET", f"{API}/api/v1/auth/me", token)
    org = DEMO_ORG if DEMO_ORG else me.get("org_id", "")
    print(f"org={org} (user org={me.get('org_id')})")

    all_rules = req("GET", f"{API}/api/v1/orgs/{org}/rules", token)
    if not isinstance(all_rules, list):
        all_rules = []

    by_name = {r["name"]: r for r in all_rules if str(r.get("name", "")).startswith("Démo")}

    # [P.131] Resolve counter camera(s) dynamically — no hardcoded UUID.
    for spec in RULES:
        if spec.get("counter") and not spec.get("camera_id"):
            resolved = resolve_counter_camera(
                token, org, spec.get("counter_camera_hint", ""), by_name.get(spec["name"])
            )
            spec["camera_id"] = resolved
            print(f"resolved counter camera for '{spec['name']}': {resolved}")

    mail_before = mail_count()
    alerts_before = count_alerts(token, org)
    original_video = get_active_demo_video(token, org)
    print(f"original active demo video: {original_video}")
    disable_all(token, org, all_rules)
    time.sleep(8)
    wait_active_rules(0)

    results: list[dict] = []
    pass_n = fail_n = 0

    for spec in RULES:
        name = spec["name"]
        if VALIDATE_ONLY and name not in VALIDATE_ONLY:
            if name == "Démo · Excès de vitesse" and os.environ.get("SPEED_DEFERRED", "0") == "1":
                results.append({
                    "rule": name,
                    "event_types": spec["event_types"],
                    "status": "SKIPPED",
                    "detail": "deferred: zone Zone_distance_parcourue hors trafic [A.1]",
                    "new_count": 0,
                    "new_alerts": 0,
                })
            continue
        event_types = spec["event_types"]
        rule = by_name.get(name)
        if not rule:
            results.append({"rule": name, "status": "FAIL", "detail": "rule missing in DB"})
            fail_n += 1
            continue

        print(f"\n=== {name} ===")
        disable_all(token, org, all_rules)
        time.sleep(5)
        wait_active_rules(0)

        # [B.24]/[D.35] Switch mono-camera demo ingestion to this scenario's camera
        # via its backing video, so the orchestrator auto-starts it with behaviors.
        scenario_cam = spec.get("camera_id") or rule_camera_id(rule)
        scenario_video = camera_video_id(token, org, scenario_cam) if scenario_cam else None

        needs_frigate = os.environ.get("EVIDENCE_BACKEND", "frigate").strip().lower() in (
            "frigate", "hybrid",
        ) or os.environ.get("FRIGATE_EVIDENCE", "true").lower() in ("true", "1")
        needs_phone = name == "Démo · Téléphone au volant" or "phone" in str(event_types)

        pf_ok, pf_detail = ensure_rule_test_ready(
            token,
            org,
            name,
            camera_id=str(scenario_cam) if scenario_cam else None,
            video_id=scenario_video,
            needs_frigate=needs_frigate,
            needs_phone_model=needs_phone,
        )
        if not pf_ok:
            results.append({
                "rule": name,
                "event_types": event_types,
                "status": "FAIL",
                "detail": pf_detail,
                "new_count": 0,
                "new_alerts": 0,
                "preflight_blocked": True,
            })
            fail_n += 1
            continue

        if not scenario_video:
            print(f"WARN: no video resolved for camera {scenario_cam}")

        # Take a timestamp baseline so count_demo_events can use "since" filtering.
        # This avoids the limit=100 cap bug when >100 events exist before the test.
        _evt_baseline_ts = datetime.now(timezone.utc).isoformat()
        evt_baseline = 0  # unused when since_iso is set
        ctr_baseline = (
            max(
                count_line_counter(token, org, spec["camera_id"]),
                count_observation_counter(token, org, spec["camera_id"]),
            )
            if spec.get("counter") and spec.get("camera_id")
            else 0
        )
        alerts_baseline_ids = list_demo_alert_ids(token, org)
        alerts_baseline = len(alerts_baseline_ids)
        mail_rule_before = mail_count()

        if name == "Démo · Feu rouge":
            refresh_feux_stream()

        set_rule(token, org, rule["id"], True)
        wait_active_rules(1, sec=180)
        print(f"rules-engine sync wait {SYNC_WAIT}s…")
        time.sleep(SYNC_WAIT)

        deadline = time.time() + TIMEOUT
        new_count = 0
        detail_parts: list[str] = []
        while time.time() < deadline:
            if time.time() - token_at > 240:
                token = login_token()
                token_at = time.time()
            evt_now = count_demo_events(token, org, event_types, since_iso=_evt_baseline_ts)
            new_count = evt_now
            if spec.get("counter") and spec.get("camera_id"):
                ctr_now = max(
                    count_line_counter(token, org, spec["camera_id"]),
                    count_observation_counter(token, org, spec["camera_id"]),
                )
                new_count = max(new_count, max(0, ctr_now - ctr_baseline))
            if new_count >= TARGET:
                break
            time.sleep(8)

        # [H.72]/[A.9] Evidence capture is async — wait for alerts after events land.
        alert_wait = int(os.environ.get("ALERT_WAIT_SEC", "120"))
        if new_count >= TARGET and spec.get("require_alert", True):
            alert_deadline = time.time() + alert_wait
            while time.time() < alert_deadline:
                if len(list_demo_alert_ids(token, org) - alerts_baseline_ids) >= 1:
                    break
                time.sleep(8)

        status = "PASS" if new_count >= TARGET else "FAIL"
        if new_count < TARGET:
            detail_parts.append(f"new_events={new_count}/{TARGET}")

        new_alerts = len(list_demo_alert_ids(token, org) - alerts_baseline_ids)
        mail_delta = 0
        if spec.get("mail") and new_count >= TARGET:
            for _ in range(12):
                time.sleep(5)
                mail_delta = mail_count() - mail_rule_before
                if mail_delta >= 1:
                    break

        require_alert = spec.get("require_alert", True)
        if status == "PASS" and require_alert and new_alerts < 1:
            if mail_delta >= 1:
                detail_parts.append(f"mail+{mail_delta} (alert async)")
            else:
                status = "FAIL"
                detail_parts.append(f"alerts={new_alerts}, events={new_count}")

        if spec.get("mail") and status == "PASS":
            if mail_delta < 1:
                for _ in range(6):
                    time.sleep(5)
                    mail_delta = mail_count() - mail_rule_before
                    if mail_delta >= 1:
                        break
            if mail_delta < 1:
                status = "FAIL"
                detail_parts.append("no_mail")
            else:
                detail_parts.append(f"mail+{mail_delta}")

        if status == "PASS" and require_alert and spec.get("name") != "Démo · Comptage véhicules":
            alert = latest_demo_alert(token, org, alerts_baseline_ids)
            if alert:
                cabin = any(
                    et in ("seatbelt_violation", "phone_use_violation")
                    for et in event_types
                )
                ev_ok, ev_reason = alert_evidence_ok(alert, require_plate=not cabin)
                if not ev_ok:
                    status = "PARTIAL"
                    detail_parts.append(f"evidence:{ev_reason}")
            else:
                detail_parts.append("no_alert_for_evidence_audit")

        if status == "PASS":
            pass_n += 1
        else:
            fail_n += 1

        detail = ", ".join(detail_parts) if detail_parts else f"new_count={new_count}"
        print(f"{name}: {status} ({detail})")
        results.append({
            "rule": name,
            "event_types": event_types,
            "status": status,
            "detail": detail,
            "new_count": new_count,
            "new_alerts": new_alerts,
        })
        set_rule(token, org, rule["id"], False)
        time.sleep(5)

    disable_all(token, org, all_rules)
    wait_active_rules(0)
    if original_video:
        try:
            set_active_demo_video(token, org, original_video)
            print(f"restored active demo video -> {original_video}")
        except Exception as exc:
            print(f"WARN: could not restore demo video: {exc}")

    speed_skipped = any(
        r.get("rule") == "Démo · Excès de vitesse" and r.get("status") == "SKIPPED"
        for r in results
    )
    validated_n = len([r for r in results if r.get("status") in ("PASS", "FAIL", "SKIPPED")])
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pass": pass_n,
        "fail": fail_n,
        "passed_rules": pass_n,
        "total_rules": validated_n or len(RULES),
        "phase_a_mode": f"{pass_n}/5",
        "speed_deferred": speed_skipped,
        "handoff": "all_demo_rules_disabled",
        "results": results,
        "rules": _results_to_rules_map(results),
    }
    report_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Demo Five Rules — E2E Report",
        "",
        f"Generated: {summary['generated_at']}",
        f"**PASS:** {pass_n} / **FAIL:** {fail_n} (target: {TARGET} detections/rule)",
        "",
        "## Handoff",
        "",
        "Les 5 règles démo sont **désactivées** après validation (`is_enabled=false`).",
        "Réactivation live : UI Règles ou `scripts/seed-demo-rules.sh`.",
        "",
        "## Résultats",
        "",
        "| Rule | Events | Status | Detail |",
        "|------|--------|--------|--------|",
    ]
    for r in results:
        et = ", ".join(r.get("event_types", []))
        lines.append(f"| {r['rule']} | {et} | {r['status']} | {r.get('detail', '')} |")
    lines.extend([
        "",
        "## Détail par règle",
        "",
    ])
    for r in results:
        lines.append(f"### {r['rule']}")
        lines.append(f"- **Status:** {r['status']}")
        lines.append(f"- **New demo events:** {r.get('new_count', 0)}")
        lines.append(f"- **New alerts:** {r.get('new_alerts', 0)}")
        lines.append(f"- **Detail:** {r.get('detail', '')}")
        lines.append("")
    lines.extend([
        "## Diagnostics runtime",
        "",
        "- **Spatial AI:** `bash scripts/force-spatial-reload.sh` (behaviors feu/vitesse sur caméras Feux + Ligne Continue).",
        "- **Rules-engine actions:** URLs internes corrigées → `/api/v1/internal/orgs/{orgID}/...` (evidence, mail, clip).",
        "- **Feu rouge:** la règle écoute `red_light_violation` (synergie véhicule en mouvement + feu rouge), pas `traffic_light_state` seul.",
        "- **Vitesse:** `speeding` via traverse zone `Zone_distance_parcourue` (calibration arêtes, limite 30 km/h).",
        "- **Comptage:** compteur `Ligne_count` via API `/lines/counters`.",
        "",
        "## Notes pipeline",
        "",
        "- **Feu rouge** : nécessite `red_light_violation` (véhicule en mouvement dans Zone_Observation pendant feu rouge).",
        "  `traffic_light_state` seul ne suffit pas pour la règle.",
        "- **Vitesse** : `speeding` via timing zone `Zone_distance_parcourue` (calibration arêtes, limite 30 km/h).",
        "- **Comptage** : compteur ligne `Ligne_count` (API `/lines/counters`).",
        "- Prérequis spatial : `bash scripts/force-spatial-reload.sh` si behaviors absents côté AI.",
        "",
        f"JSON détaillé : `logs/demo-five-rules-report.json`",
    ])
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))

    if fail_n > 0:
        print(f"\nVALIDATION FAILED ({fail_n} rules)", file=sys.stderr)
        return 1
    print("\nVALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
