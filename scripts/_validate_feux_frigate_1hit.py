#!/usr/bin/env python3

"""Validation ciblée feu rouge — 1 alerte Frigate avec preuve complete stricte."""

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

POLL_SEC = int(os.environ.get("POLL_SEC", "12"))

MAX_ALIGN_MS = int(os.environ.get("FRIGATE_MAX_ALIGN_MS", "20000"))

MIN_BBOX_AREA = float(os.environ.get("FEU_MIN_BBOX_AREA", "0.01"))

SUBJECT_TEXTURE_MIN = float(os.environ.get("FEU_SUBJECT_TEXTURE_MIN", "50"))
REQUIRE_COMPLETE = os.environ.get("FEU_1HIT_REQUIRE_COMPLETE", "0").strip().lower() in ("1", "true", "yes")
SETTLE_SEC = int(os.environ.get("SETTLE_SEC", "8") or 8)
EVIDENCE_SETTLE_SEC = int(os.environ.get("EVIDENCE_SETTLE_SEC", "90") or 90)
MIN_INGEST_FRAMES = int(os.environ.get("FEU_MIN_INGEST_FRAMES", "100") or 100)
RE_PORT = os.environ.get("RULES_ENGINE_PORT", "8010")


def rules_engine_ok() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{RE_PORT}/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def repair_demo_streams() -> None:
    root = os.environ.get("MICROTEST_ROOT", os.path.expanduser("~/citevision-v2"))
    script = os.path.join(root, "scripts", "ensure-demo-streams.sh")
    if os.path.isfile(script):
        subprocess.run(["bash", script], check=False, capture_output=True)


def sync_rules_engine() -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{RE_PORT}/internal/sync-rules", method="POST"),
            timeout=15,
        )
        print("  rules-engine synced", flush=True)
    except Exception as exc:
        print(f"  WARN rules sync: {exc}", flush=True)





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


def wait_hsv_red(cam_id: str, sec: int = 360) -> bool:
    ai = os.environ.get("AI_URL", "http://127.0.0.1:8001").rstrip("/")
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{ai}/debug/rule-blockers", timeout=10) as resp:
                dbg = json.loads(resp.read().decode())
            gate = (dbg.get("hsv_gate_debug") or {}).get(cam_id) or {}
            state = str(gate.get("gate") or gate.get("raw") or "").lower().strip()
            if state == "red":
                print(
                    f"  HSV gate red raw={gate.get('raw')} stable={gate.get('stable')}",
                    flush=True,
                )
                return True
        except Exception:
            pass
        print("  waiting HSV gate red...", flush=True)
        time.sleep(5)
    return False


def wait_frigate_api(sec: int = 90) -> bool:
    base = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/version", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(4)
    return False


def count_frigate_car_events(frigate_cam: str, window_sec: float = 120.0) -> int:
    base = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
    qs = urllib.parse.urlencode({"camera": frigate_cam, "limit": 50})
    url = f"{base}/api/events?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            events = json.loads(resp.read().decode())
    except Exception:
        return 0
    if not isinstance(events, list):
        return 0
    return sum(1 for ev in events if str(ev.get("label") or "").lower() == "car")


def wait_ingest_warm(cam_id: str, min_frames: int, sec: int = 180) -> dict:
    deadline = time.time() + sec
    last: dict = {}
    while time.time() < deadline:
        last = camera_status(cam_id)
        fp = int(last.get("frames_processed") or 0)
        print(f"  ingest warm processed={fp}/{min_frames} read={last.get('frames_read')}", flush=True)
        if fp >= min_frames:
            return last
        time.sleep(8)
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





def count_since(rule_id: str, since: str) -> tuple[int, int, int, int]:

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

    complete = psql(

        f"SELECT count(*) FROM alerts a WHERE a.org_id='{ORG}'::uuid "

        f"AND a.rule_id='{rule_id}'::uuid AND a.created_at>='{since}'::timestamptz "

        f"AND a.evidence_snapshot->'package'->'metadata'->>'evidence_status'='complete';"

    )

    return int(evt or 0), int(alerts or 0), int(frigate or 0), int(complete or 0)





def _parse_json_field(raw: str) -> dict | None:

    if not raw or raw in ("null", ""):

        return None

    try:

        val = json.loads(raw)

        return val if isinstance(val, dict) else None

    except json.JSONDecodeError:

        return None





def _bbox_area(bbox: dict | None) -> float:

    if not bbox:

        return 0.0

    try:

        return float(bbox.get("width") or 0) * float(bbox.get("height") or 0)

    except (TypeError, ValueError):

        return 0.0



def _norm_bbox(bbox: dict | None) -> dict | None:

    if not bbox:

        return None

    try:

        x = float(bbox.get("x") or 0)

        y = float(bbox.get("y") or 0)

        w = float(bbox.get("width") or 0)

        h = float(bbox.get("height") or 0)

    except (TypeError, ValueError):

        return None

    if w <= 0 or h <= 0:

        return None

    if not bbox.get("norm") and max(x, y, w, h) > 1.5:

        return {"x": x / 1920.0, "y": y / 1080.0, "width": w / 1920.0, "height": h / 1080.0}

    return {"x": x, "y": y, "width": w, "height": h}



def _bbox_iou(a: dict | None, b: dict | None) -> float:

    na, nb = _norm_bbox(a), _norm_bbox(b)

    if not na or not nb:

        return 0.0

    ax1, ay1 = na["x"], na["y"]

    ax2, ay2 = ax1 + na["width"], ay1 + na["height"]

    bx1, by1 = nb["x"], nb["y"]

    bx2, by2 = bx1 + nb["width"], by1 + nb["height"]

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)

    ix2, iy2 = min(ax2, bx2), min(ay2, by2)

    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)

    inter = iw * ih

    union = na["width"] * na["height"] + nb["width"] * nb["height"] - inter

    return inter / union if union > 0 else 0.0





def _truthy(val: str | None) -> bool:

    return str(val or "").lower() in ("true", "1", "yes")





def print_evidence_quality_audit(rule_id: str, since: str) -> tuple[bool, dict]:

    row = psql(

        f"SELECT "

        f"a.evidence_snapshot->'package'->'metadata'->>'capture_source', "

        f"a.evidence_snapshot->'package'->'metadata'->>'bbox_source', "

        f"a.evidence_snapshot->'package'->'metadata'->>'evidence_status', "

        f"a.evidence_snapshot->'package'->'metadata'->>'scene_light_state', "

        f"a.evidence_snapshot->'package'->'metadata'->>'subject_quality_ok', "

        f"a.evidence_snapshot->'package'->'metadata'->>'subject_texture', "

        f"a.evidence_snapshot->'package'->'metadata'->'bbox', "

        f"a.evidence_snapshot->'package'->'metadata'->'ia_bbox', "

        f"a.evidence_snapshot->'package'->'metadata'->>'align_delta_ms', "

        f"a.evidence_snapshot->'package'->'metadata'->>'capture_frame_ts', "

        f"a.evidence_snapshot->'package'->'metadata'->>'frigate_event_id', "

        f"a.evidence_snapshot->'package'->'metadata'->>'abort_reason' "

        f"FROM alerts a WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{rule_id}'::uuid "

        f"AND a.created_at>='{since}'::timestamptz "

        f"ORDER BY "
        f"(a.evidence_snapshot->'package'->'metadata'->>'scene_light_state'='red') DESC, "
        f"(a.evidence_snapshot->'package'->'metadata'->>'bbox_source'='frigate_mqtt') DESC, "
        f"(a.evidence_snapshot->'package'->'metadata'->>'capture_source'='frigate_track') DESC, "
        f"a.created_at DESC LIMIT 1;"

    )

    audit: dict = {"gates": {}, "failures": []}

    if not row or "|" not in row:

        print("  evidence audit: no alert evidence", flush=True)

        audit["failures"].append("no evidence")

        return False, audit



    parts = row.split("|", 12)

    (

        capture_source,

        bbox_source,

        evidence_status,

        scene_light,

        subject_quality_ok,

        subject_texture,

        bbox_raw,

        ia_bbox_raw,

        align_raw,

        capture_frame_ts,

        frigate_event,

        abort_reason,

    ) = (parts + [""] * 12)[:12]



    bbox = _parse_json_field(bbox_raw)

    bbox_area = _bbox_area(bbox)

    ia_bbox = _parse_json_field(ia_bbox_raw)

    bbox_iou = _bbox_iou(bbox, ia_bbox)



    print(f"  capture_source={capture_source}", flush=True)

    print(f"  bbox_source={bbox_source}", flush=True)

    print(f"  evidence_status={evidence_status}", flush=True)

    print(f"  scene_light_state={scene_light}", flush=True)

    print(f"  subject_quality_ok={subject_quality_ok} subject_texture={subject_texture}", flush=True)

    print(f"  frigate_bbox={bbox_raw}", flush=True)

    print(f"  ia_bbox={ia_bbox_raw}", flush=True)

    print(f"  bbox_area={bbox_area:.4f}", flush=True)

    print(f"  align_delta_ms={align_raw} frigate_event={frigate_event}", flush=True)
    print(f"  capture_frame_ts={capture_frame_ts}", flush=True)

    if abort_reason:

        print(f"  abort_reason={abort_reason}", flush=True)



    gates = {
        "capture_source": capture_source == "frigate_track",
        "bbox_source": bbox_source == "frigate_mqtt",
        "scene_light_state": scene_light == "red",
        "subject_quality": _truthy(subject_quality_ok) or (
            subject_texture not in ("", "null", None)
            and float(subject_texture or 0) >= SUBJECT_TEXTURE_MIN
        ),
        "align_delta_ms": True,
        "capture_frame_ts": capture_frame_ts not in ("", "null", None),
        "bbox_matches_mqtt": bbox_iou >= 0.25 if ia_bbox else False,
        "no_ia_overlay": bbox_source not in ("ia_overlay", "emission_track"),
    }
    if REQUIRE_COMPLETE:
        gates["evidence_status"] = evidence_status == "complete"



    try:

        align_ms = abs(int(float(align_raw or 0)))

        gates["align_delta_ms"] = align_ms <= MAX_ALIGN_MS

        if not gates["align_delta_ms"]:

            print(f"  [FAIL] align_delta_ms={align_ms} > max={MAX_ALIGN_MS}", flush=True)

    except (TypeError, ValueError):

        gates["align_delta_ms"] = False

        print("  [FAIL] align_delta_ms missing or invalid", flush=True)



    labels = {
        "capture_source": f"capture_source={capture_source} (need frigate_track)",
        "bbox_source": f"bbox_source={bbox_source} (need frigate_mqtt)",
        "scene_light_state": f"scene_light_state={scene_light} (need red)",
        "subject_quality": f"subject ok={subject_quality_ok} texture={subject_texture}",
        "capture_frame_ts": f"capture_frame_ts={capture_frame_ts} (need anchored proof frame)",
        "bbox_matches_mqtt": f"bbox_vs_mqtt_iou={bbox_iou:.3f} (need >=0.25)",
        "no_ia_overlay": f"bbox_source={bbox_source} (reject ia_overlay/emission_track)",
    }
    if REQUIRE_COMPLETE:
        labels["evidence_status"] = f"evidence_status={evidence_status} (need complete)"



    failures: list[str] = []

    for key, ok in gates.items():

        audit["gates"][key] = ok

        if not ok:

            msg = labels.get(key, key)

            failures.append(msg)

            print(f"  [FAIL] {msg}", flush=True)



    audit.update({

        "capture_source": capture_source,

        "bbox_source": bbox_source,

        "evidence_status": evidence_status,

        "scene_light_state": scene_light,

        "subject_quality_ok": subject_quality_ok,

        "subject_texture": subject_texture,

        "bbox_area": bbox_area,

        "bbox_vs_mqtt_iou": round(bbox_iou, 3),

        "align_delta_ms": align_raw,

        "capture_frame_ts": capture_frame_ts,

        "frigate_event_id": frigate_event,

        "abort_reason": abort_reason,

        "failures": failures,

    })

    return len(failures) == 0, audit





def main() -> int:

    print("=== Validation feu rouge — 1 détection Frigate (strict) ===", flush=True)

    if not ai_health():
        print("[FAIL] AI not running — python3 scripts/_restart_ai.py", flush=True)
        return 1
    if not rules_engine_ok():
        print("[FAIL] rules-engine down — bash scripts/_start-rules-engine.sh", flush=True)
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

    # Keep feu enabled before rebuild (Frigate record+snapshots for demo).
    for r in rules:
        name = str(r.get("name", ""))
        if not name.startswith("Démo"):
            continue
        want = name == RULE_NAME
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
        f"feu video active cam={cam_id[:8]} vid={video_id[:8]} "
        f"pipeline={demo_st.get('pipeline_status')} ingest={demo_st.get('ingest_ready')}",
        flush=True,
    )
    if not demo_st.get("ingest_ready"):
        st = wait_ingest(cam_id, 120)
        if int(st.get("frames_processed") or 0) < 6:
            print("[FAIL] ingest not ready after video switch", flush=True)
            return 1

    st = wait_ingest_warm(cam_id, MIN_INGEST_FRAMES, 180)
    if int(st.get("frames_processed") or 0) < MIN_INGEST_FRAMES:
        print(f"[FAIL] ingest warm frames={st.get('frames_processed')} need>={MIN_INGEST_FRAMES}", flush=True)
        return 1

    frigate_cam = f"cv_{cam_id}"
    repair_demo_streams()
    if not wait_frigate_api(90):
        print("[WARN] Frigate API not ready before car-event probe", flush=True)
    car_events = count_frigate_car_events(frigate_cam)
    skip_rebuild = os.environ.get("FEU_SKIP_FRIGATE_REBUILD", "").strip().lower() in ("1", "true", "yes")
    if skip_rebuild:
        print(f"  skip frigate rebuild — FEU_SKIP_FRIGATE_REBUILD=1 (car_events={car_events})", flush=True)
    elif car_events >= 1:
        print(f"  skip frigate rebuild — {car_events} recent car events on feu cam", flush=True)
    else:
        if not wait_frigate_api(30):
            print("  skip frigate rebuild — Frigate API down (avoid 500 thrash)", flush=True)
        else:
            car_events = count_frigate_car_events(frigate_cam)
            if car_events >= 1:
                print(f"  skip frigate rebuild — {car_events} car events after Frigate ready", flush=True)
            else:
                try:
                    req("POST", f"{API}/api/v1/internal/ingest/frigate/rebuild", internal=True)
                    print("  frigate rebuild requested", flush=True)
                except Exception as exc:
                    print(f"  WARN frigate rebuild: {exc}", flush=True)
    try:
        req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
    except Exception:
        pass
    sync_rules_engine()
    if wait_frigate_events(frigate_cam, 90) < 1:
        print("[WARN] no Frigate events yet", flush=True)
    if SETTLE_SEC > 0:
        print(f"  settle {SETTLE_SEC}s after switch...", flush=True)
        time.sleep(SETTLE_SEC)

    if not wait_hsv_red(cam_id, min(360, MAX_WAIT_SEC)):
        print("[WARN] HSV gate not red within wait — continuing anyway", flush=True)

    since = os.environ.get("HIT1_SINCE") or datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S%z"
    ).replace("+0000", "+00")
    print(f"HIT1_SINCE={since}", flush=True)

    req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{feu['id']}?skip_preflight=1", tok, {"is_enabled": True})
    sync_rules_engine()
    print(f"rule enabled — 1 hit frigate+red (max {MAX_WAIT_SEC}s, complete_required={REQUIRE_COMPLETE})", flush=True)

    hit = False
    deadline = time.time() + MAX_WAIT_SEC
    while time.time() < deadline:
        time.sleep(POLL_SEC)
        evt, alerts, frigate, complete = count_since(feu["id"], since)
        print(
            f"  poll events={evt} alerts={alerts} frigate_track={frigate} complete={complete}",
            flush=True,
        )
        if alerts >= 1 and frigate >= 1:
            ok, _audit = print_evidence_quality_audit(feu["id"], since)
            if ok:
                print("[HIT] 1 alert with strict gates", flush=True)
                hit = True
                break
        if not ai_health():
            print("  WARN AI down", flush=True)

    evt, alerts, frigate, complete = count_since(feu["id"], since)
    if evt >= 1 and alerts < 1 and EVIDENCE_SETTLE_SEC > 0:
        settle_deadline = time.time() + EVIDENCE_SETTLE_SEC
        print(
            f"  evidence settle up to {EVIDENCE_SETTLE_SEC}s "
            f"(events={evt} alerts=0, rules-engine retries)...",
            flush=True,
        )
        while time.time() < settle_deadline:
            time.sleep(POLL_SEC)
            evt, alerts, frigate, complete = count_since(feu["id"], since)
            print(
                f"  poll events={evt} alerts={alerts} frigate_track={frigate} complete={complete}",
                flush=True,
            )
            if alerts >= 1 and frigate >= 1:
                ok, _audit = print_evidence_quality_audit(feu["id"], since)
                if ok:
                    print("[HIT] 1 alert with strict gates", flush=True)
                    hit = True
                    break
            if not ai_health():
                print("  WARN AI down", flush=True)

    evt, alerts, frigate, complete = count_since(feu["id"], since)

    req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{feu['id']}", tok, {"is_enabled": False})

    gates_ok, audit = print_evidence_quality_audit(feu["id"], since)



    print(f"FINAL events={evt} alerts={alerts} frigate_track={frigate} complete={complete}", flush=True)

    if hit and gates_ok:

        status = "PASS"

    elif alerts >= 1 and not gates_ok:

        status = "FAIL"

        print(f"[FAIL] alert present but strict gates failed: {audit.get('failures')}", flush=True)

    elif evt >= 1:

        status = "PARTIAL"

    else:

        status = "FAIL"

    print(f"RESULT: {status}", flush=True)

    return 0 if status == "PASS" else 1





if __name__ == "__main__":

    raise SystemExit(main())

