#!/usr/bin/env python3
"""Smoke POST /evidence/request on Frigate car event — strict feu gates."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081").rstrip("/")
FRIGATE = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
RULE_NAME = os.environ.get("RULE_NAME", "Démo · Feu rouge")
TEXTURE_MIN = float(os.environ.get("FEU_SUBJECT_TEXTURE_MIN", "50") or 50)
CAM_ID = os.environ.get("FEU_CAMERA_ID", "").strip()
WAIT_SEC = int(os.environ.get("FEU_SMOKE_WAIT_SEC", "120") or 120)


def req(method: str, url: str, token: str | None = None, body: dict | None = None, *, internal: bool = False):
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


def rule_camera_id(rule: dict) -> str:
    defn = rule.get("definition") or {}
    if isinstance(defn, str):
        defn = json.loads(defn)
    cam = defn.get("camera_id")
    if cam:
        return str(cam)
    return str((defn.get("bindings") or {}).get("camera_id") or "")


def _zone_behavior(z: dict) -> str:
    behavior = str(z.get("behavior") or z.get("zone_kind") or "")
    if behavior:
        return behavior
    cfg = z.get("behavior_config")
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except json.JSONDecodeError:
            cfg = {}
    if isinstance(cfg, dict):
        return str(cfg.get("behavior") or "")
    return ""


def light_polygon_from_zones(zones: list, cam_id: str) -> list:
    for z in zones:
        if not isinstance(z, dict):
            continue
        zcam = str(z.get("camera_id") or "")
        if zcam and zcam != cam_id:
            continue
        if _zone_behavior(z) not in ("traffic_light_color", "red_light_control"):
            continue
        poly = z.get("polygon") or z.get("points") or []
        if poly:
            return poly if isinstance(poly, list) else json.loads(poly)
    return []


def light_polygon(spatial: dict) -> list:
    return light_polygon_from_zones(spatial.get("zones") or [], str(spatial.get("camera_id") or ""))


def snapshot_light_state(jpeg: bytes, poly: list) -> str:
    if not jpeg or not poly:
        return "unknown"
    try:
        from citevision_ai.frigate_bridge.snapshot import classify_snapshot_light_state
        return classify_snapshot_light_state(jpeg, poly)
    except Exception:
        return "unknown"


def list_car_events(frigate_cam: str) -> list[dict]:
    qs = urllib.parse.urlencode({"camera": frigate_cam, "limit": 40})
    with urllib.request.urlopen(f"{FRIGATE}/api/events?{qs}", timeout=12) as resp:
        events = json.loads(resp.read().decode())
    if not isinstance(events, list):
        return []
    out = [ev for ev in events if str(ev.get("label") or "").lower() == "car"]
    out.sort(key=lambda e: float(e.get("start_time") or 0), reverse=True)
    return out


def pick_event(cars: list[dict], light_poly: list) -> tuple[dict | None, str]:
    for ev in cars:
        if ev.get("end_time") is None:
            continue
        eid = str(ev.get("id") or "")
        if not eid:
            continue
        try:
            with urllib.request.urlopen(f"{FRIGATE}/api/events/{eid}/snapshot.jpg", timeout=12) as resp:
                snap = resp.read()
            if snapshot_light_state(snap, light_poly) == "red":
                return ev, "snapshot_red"
        except Exception:
            continue
    return (None, "none")


def build_payload(ev: dict, cam_id: str, meta_poly: list, *, snapshot_red: bool) -> dict:
    event_id = str(ev.get("id") or "")
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    box = data.get("box")
    bbox = None
    if isinstance(box, (list, tuple)) and len(box) >= 4:
        bbox = {"x": box[0], "y": box[1], "width": box[2], "height": box[3], "norm": True}
    path_data = data.get("path_data") or []
    bbox_ts = path_data[-1][1] if path_data else ev.get("start_time")
    metadata = {
        "bridge_source": "frigate",
        "frigate_event_id": event_id,
        "light_zone_polygon": meta_poly,
        "bbox": bbox,
        "bbox_source": "frigate_mqtt",
    }
    if snapshot_red:
        metadata.update({
            "frigate_snapshot_light_state": "red",
            "hsv_light_state": "red",
            "light_state": "red",
        })
    return {
        "event_id": str(uuid.uuid4()),
        "camera_id": cam_id,
        "event_type": "red_light_violation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bbox_ts": bbox_ts,
        "bbox": bbox,
        "class_name": "car",
        "confidence": 0.9,
        "frigate_event_id": event_id,
        "metadata": metadata,
    }


def main() -> int:
    tok = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})["access_token"]
    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
    feu = next((r for r in rules if r.get("name") == RULE_NAME), None)
    if not feu:
        print("[NO-GO] feu rule missing", flush=True)
        return 2
    cam_id = CAM_ID or rule_camera_id(feu)
    if not cam_id:
        print("[NO-GO] feu camera_id missing", flush=True)
        return 2
    frigate_cam = f"cv_{cam_id}"
    meta_poly: list = []
    try:
        zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", tok)
        meta_poly = light_polygon_from_zones(zones if isinstance(zones, list) else [], cam_id)
    except Exception:
        pass
    if not meta_poly:
        try:
            spatial = req("GET", f"http://127.0.0.1:8001/cameras/{cam_id}/spatial")
            meta_poly = light_polygon(spatial)
        except Exception:
            pass
    if not meta_poly:
        print("[NO-GO] traffic_light_color polygon missing", flush=True)
        return 2

    ev_policy = {
        "enabled": True,
        "clip_seconds": 6,
        "images": [
            {"role": "scene", "crop": "full"},
            {"role": "subject", "crop": "bbox", "padding_pct": 10, "zoom": 2.2},
            {"role": "plate", "crop": "plate_rear", "padding_pct": 6, "zoom": 1.8},
        ],
    }

    deadline = time.time() + WAIT_SEC
    last_fail = ""
    while time.time() < deadline:
        cars = list_car_events(frigate_cam)
        ev, pick_reason = pick_event(cars, meta_poly)
        if not ev or pick_reason != "snapshot_red":
            print("  smoke waiting for car event with snapshot red...", flush=True)
            time.sleep(8)
            continue
        event_id = str(ev.get("id") or "")
        print(f"smoke pick={pick_reason} event={event_id[:24]} end={ev.get('end_time')}", flush=True)
        payload = build_payload(ev, cam_id, meta_poly, snapshot_red=True)
        try:
            raw = req(
                "POST",
                f"{API}/api/v1/internal/orgs/{ORG}/evidence/request",
                body={"camera_id": cam_id, "event": payload, "evidence": ev_policy},
                internal=True,
            )
        except urllib.error.HTTPError as exc:
            last_fail = f"HTTP {exc.code}: {exc.read().decode()[:200]}"
            print(f"  smoke HTTP error: {last_fail}", flush=True)
            time.sleep(8)
            continue
        except Exception as exc:
            last_fail = str(exc)
            print(f"  smoke error: {last_fail}", flush=True)
            time.sleep(8)
            continue

        if raw.get("error"):
            last_fail = str(raw.get("error"))
            print(f"  smoke api error: {last_fail}", flush=True)
            time.sleep(8)
            continue

        pkg = raw.get("package") or (raw.get("evidence") or {}).get("package") or {}
        if not isinstance(pkg, dict):
            pkg = {}
        meta = pkg.get("metadata") or {}
        if not pkg:
            last_fail = f"empty_response keys={list(raw.keys())}"
            print(f"  smoke empty raw={json.dumps(raw)[:240]}", flush=True)
            time.sleep(8)
            continue

        abort = meta.get("abort_reason")
        texture = meta.get("subject_texture")
        capture = meta.get("capture_source")
        scene = meta.get("scene_light_state")
        clip = pkg.get("clip") or {}
        has_clip = bool(clip.get("url") or clip.get("asset_id"))
        roles = {str(i.get("role")) for i in (pkg.get("images") or []) if isinstance(i, dict)}
        print(
            f"smoke frigate_event={event_id[:24]} capture={capture} scene={scene} "
            f"texture={texture} clip={has_clip} abort={abort}",
            flush=True,
        )
        failures: list[str] = []
        if capture != "frigate_track":
            failures.append(f"capture_source={capture}")
        if scene != "red":
            failures.append(f"scene_light_state={scene}")
        if texture is None or float(texture) < TEXTURE_MIN:
            failures.append(f"texture={texture}")
        if not has_clip:
            failures.append("clip_missing")
        if abort:
            failures.append(f"abort={abort}")
        if "scene" not in roles or "subject" not in roles:
            failures.append(f"images={sorted(roles)}")
        if not failures:
            print("[OK] smoke feu evidence PASS", flush=True)
            return 0
        last_fail = ", ".join(failures)
        print(f"  smoke retry ({last_fail})", flush=True)
        time.sleep(8)

    print(f"[NO-GO] smoke timeout after {WAIT_SEC}s last={last_fail}", flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
