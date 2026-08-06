#!/usr/bin/env python3
"""Galerie diagnostic 1-hit feu rouge — preuves backend + snapshots Frigate bruts."""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("MICROTEST_ROOT", Path.home() / "citevision-v2"))
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081").rstrip("/")
FRIGATE = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
TS = os.environ.get("HIT1_TS") or os.environ.get("TS") or ""
SINCE = os.environ.get("HIT1_SINCE") or ""
RULE_NAME = "Démo · Feu rouge"
LIMIT = max(1, int(os.environ.get("HIT1_EXPORT_LIMIT", "3") or 3))
MAX_ALIGN_MS = int(os.environ.get("FRIGATE_MAX_ALIGN_MS", "20000"))
MIN_BBOX_AREA = float(os.environ.get("FEU_MIN_BBOX_AREA", "0.01"))
SUBJECT_TEXTURE_MIN = float(os.environ.get("FEU_SUBJECT_TEXTURE_MIN", "50"))


def _parse_bbox(raw) -> dict | None:
    if not raw or raw in ("null", ""):
        return None
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else None
    except (json.JSONDecodeError, TypeError):
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


def _truthy(val) -> bool:
    return str(val or "").lower() in ("true", "1", "yes")


def evaluate_strict_gates(meta: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    capture = str(meta.get("capture_source") or "")
    bbox_src = str(meta.get("bbox_source") or "")
    evidence = str(meta.get("evidence_status") or "")
    scene = str(meta.get("scene_light_state") or "")
    subject_ok = meta.get("subject_quality_ok")
    subject_vehicle_ok = meta.get("subject_vehicle_ok")
    texture = meta.get("subject_texture")
    bbox = _parse_bbox(meta.get("bbox"))
    ia_bbox = _parse_bbox(meta.get("ia_bbox"))
    area = _bbox_area(bbox)
    hsv = meta.get("hsv_recheck") or {}
    hsv_scene = str(hsv.get("backend_scene") or "").lower()
    bbox_iou = _bbox_iou(bbox, ia_bbox)

    checks = [
        (capture == "frigate_track", f"capture_source={capture} (need frigate_track)"),
        (bbox_src == "frigate_mqtt", f"bbox_source={bbox_src} (need frigate_mqtt)"),
        (scene == "red", f"scene_light_state={scene} (need red)"),
        (hsv_scene == "red", f"hsv_recheck.backend_scene={hsv_scene or 'missing'} (need red)"),
        (
            _truthy(subject_ok)
            and (subject_vehicle_ok is None or _truthy(subject_vehicle_ok))
            and (texture is not None and float(texture or 0) >= SUBJECT_TEXTURE_MIN),
            f"subject ok={subject_ok} vehicle_ok={subject_vehicle_ok} texture={texture}",
        ),
        (bbox_src not in ("ia_overlay", "emission_track"), f"bbox_source={bbox_src}"),
        (
            meta.get("bbox_center_in_obs") is True,
            f"bbox_center_in_obs={meta.get('bbox_center_in_obs')} (need True — centre bbox dans Zone_Observation)",
        ),
    ]
    if ia_bbox:
        checks.append((bbox_iou >= 0.25, f"bbox_vs_mqtt_iou={bbox_iou:.3f} (need >=0.25)"))
    if os.environ.get("FEU_1HIT_REQUIRE_COMPLETE", "0").strip().lower() in ("1", "true", "yes"):
        checks.insert(2, (evidence == "complete", f"evidence_status={evidence} (need complete)"))
    try:
        align_ms = abs(int(float(meta.get("align_delta_ms") or 0)))
        checks.append((align_ms <= MAX_ALIGN_MS, f"align_delta_ms={align_ms} (max {MAX_ALIGN_MS})"))
    except (TypeError, ValueError):
        checks.append((False, "align_delta_ms invalid"))

    for ok, msg in checks:
        if not ok:
            failures.append(msg)
    return len(failures) == 0, failures


def fetch_blockers_summary() -> dict:
    ai = os.environ.get("AI_URL", "http://127.0.0.1:8001").rstrip("/")
    try:
        with urllib.request.urlopen(f"{ai}/debug/rule-blockers", timeout=12) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"_error": str(exc)}


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return (r.stdout or "").strip()


def _zone_polygon_from_db(frigate_camera_id: str, where: str) -> list:
    cam = (frigate_camera_id or "").strip()
    if cam.startswith("cv_"):
        cam = cam[3:]
    if not cam:
        return []
    sql = (
        "SELECT polygon::text FROM zones "
        f"WHERE org_id='{ORG}'::uuid AND camera_id='{cam}'::uuid "
        f"AND {where} AND is_active=true LIMIT 1;"
    )
    raw = psql(sql)
    if not raw:
        return []
    try:
        poly = json.loads(raw)
        return poly if isinstance(poly, list) else []
    except json.JSONDecodeError:
        return []


def light_polygon_from_db(frigate_camera_id: str) -> list:
    return _zone_polygon_from_db(frigate_camera_id, "name='Zone_des_feux'")


def obs_polygon_from_db(frigate_camera_id: str) -> list:
    poly = _zone_polygon_from_db(frigate_camera_id, "behavior='red_light_observation'")
    if poly:
        return poly
    return _zone_polygon_from_db(frigate_camera_id, "name='Zone_Observation'")


def _poly_points(poly: list) -> list[tuple[float, float]]:
    """Normalize polygon points: accepts [{'x':..,'y':..}, ...] or [[x,y], ...]."""
    pts: list[tuple[float, float]] = []
    for p in poly or []:
        try:
            if isinstance(p, dict):
                pts.append((float(p.get("x", 0)), float(p.get("y", 0))))
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                pts.append((float(p[0]), float(p[1])))
        except (TypeError, ValueError):
            continue
    return pts


def point_in_polygon(px: float, py: float, poly: list) -> bool | None:
    pts = _poly_points(poly)
    if len(pts) < 3:
        return None
    inside = False
    j = len(pts) - 1
    for i, (xi, yi) in enumerate(pts):
        xj, yj = pts[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def draw_zones_overlay(
    scene_path: Path,
    dest_path: Path,
    light_poly: list,
    obs_poly: list,
    bbox: dict | None,
) -> bool:
    """Annotated copy of the scene: Zone_des_feux, Zone_Observation and the alert bbox."""
    try:
        import cv2
        import numpy as np

        arr = np.fromfile(str(scene_path), dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return False
        h, w = frame.shape[:2]

        def to_px(poly: list) -> "np.ndarray | None":
            pts = _poly_points(poly)
            if len(pts) < 3:
                return None
            xs = [p[0] for p in pts] + [p[1] for p in pts]
            scale = max(xs) <= 1.5
            out = [
                (int(x * w) if scale else int(x), int(y * h) if scale else int(y))
                for x, y in pts
            ]
            return np.array(out, dtype=np.int32)

        for poly, color, label in (
            (light_poly, (0, 200, 255), "Zone_des_feux"),
            (obs_poly, (80, 255, 80), "Zone_Observation"),
        ):
            px = to_px(poly)
            if px is None:
                continue
            cv2.polylines(frame, [px], True, color, 2)
            tx, ty = int(px[:, 0].min()), max(18, int(px[:, 1].min()) - 6)
            cv2.putText(frame, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        nb = _norm_bbox(bbox)
        if nb:
            x1, y1 = int(nb["x"] * w), int(nb["y"] * h)
            x2, y2 = int((nb["x"] + nb["width"]) * w), int((nb["y"] + nb["height"]) * h)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 60, 255), 2)
            cv2.putText(frame, "alert bbox", (x1, max(14, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 255), 2)

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not ok:
            return False
        dest_path.write_bytes(buf.tobytes())
        return True
    except Exception as exc:
        print(f"  overlay skip: {exc}", flush=True)
        return False


def http_get(url: str, token: str | None = None, timeout: int = 120) -> bytes:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_json(url: str, token: str | None = None) -> dict:
    raw = http_get(url, token=token, timeout=60)
    return json.loads(raw.decode()) if raw else {}


def download_backend_asset(token: str, asset_id: str, dest: Path) -> bool:
    if not asset_id:
        return False
    key = urllib.parse.quote(asset_id, safe="")
    url = f"{API}/api/v1/orgs/{ORG}/evidence/asset?key={key}"
    try:
        data = http_get(url, token=token)
        if len(data) < 200:
            return False
        dest.write_bytes(data)
        return True
    except Exception as exc:
        print(f"  backend asset fail: {exc}", flush=True)
        return False


def download_frigate(path: str, dest: Path) -> bool:
    try:
        data = http_get(f"{FRIGATE}{path}", timeout=60)
        if len(data) < 200:
            return False
        dest.write_bytes(data)
        return True
    except Exception as exc:
        print(f"  frigate {path} fail: {exc}", flush=True)
        return False


def classify_scene_light(jpeg_path: Path, poly: list) -> str | None:
    if not jpeg_path.exists() or not poly:
        return None
    try:
        import cv2
        import numpy as np
        from citevision_ai.road_enforcement.traffic_light import classify_light_color, _polygon_pixel_bbox

        arr = np.fromfile(str(jpeg_path), dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        h, w = frame.shape[:2]
        box = _polygon_pixel_bbox(poly, w, h)
        if not box:
            return None
        x1, y1, x2, y2 = box
        state, ratios = classify_light_color(frame[y1:y2, x1:x2])
        return state
    except Exception as exc:
        print(f"  hsv classify skip: {exc}", flush=True)
        return None


def main() -> int:
    if not TS:
        print("HIT1_TS or TS required", file=sys.stderr)
        return 1

    out_wsl = ROOT / "validation-evidence" / f"1hit-feu-{TS}"
    out_win = Path("/mnt/c/Users/gheno/citevision/validation-evidence") / f"1hit-feu-{TS}"
    out_wsl.mkdir(parents=True, exist_ok=True)

    tok: str | None = None
    try:
        login = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{API}/api/v1/auth/login",
                    data=json.dumps({"email": EMAIL, "password": PASS}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=30,
            ).read()
        )
        tok = login["access_token"]
    except Exception as exc:
        print(f"login failed: {exc}", flush=True)

    esc = RULE_NAME.replace("'", "''")
    rule_id = psql(
        f"SELECT id::text FROM rules WHERE org_id='{ORG}'::uuid AND name='{esc}' LIMIT 1;"
    ) if tok else ""
    if tok and not rule_id:
        print("rule not found", file=sys.stderr)
        return 1

    since_clause = f"AND a.created_at >= '{SINCE}'::timestamptz" if SINCE else ""
    rows: list[str] = []
    row_source = "alerts"
    if tok and rule_id:
        sql = (
            "SELECT a.id::text, a.created_at::text, coalesce(a.evidence_snapshot::text,'null') "
            f"FROM alerts a WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{rule_id}'::uuid "
            f"{since_clause} ORDER BY a.created_at DESC LIMIT {LIMIT};"
        )
        rows = [r for r in psql(sql).splitlines() if r.strip()]
    # Fallback: rules-engine may not have persisted alerts after a stack restart,
    # while events already carry the complete evidence_snapshot package.
    if not rows:
        row_source = "events"
        ev_since = f"AND e.occurred_at >= '{SINCE}'::timestamptz" if SINCE else ""
        sql = (
            "SELECT e.id::text, e.occurred_at::text, coalesce(e.evidence_snapshot::text,'null') "
            f"FROM events e WHERE e.org_id='{ORG}'::uuid "
            "AND e.event_type='red_light_violation' "
            f"{ev_since} ORDER BY e.occurred_at DESC LIMIT {LIMIT};"
        )
        rows = [r for r in psql(sql).splitlines() if r.strip()]
        # Last resort: most recent red_light events regardless of SINCE.
        if not rows:
            sql = (
                "SELECT e.id::text, e.occurred_at::text, coalesce(e.evidence_snapshot::text,'null') "
                f"FROM events e WHERE e.org_id='{ORG}'::uuid "
                "AND e.event_type='red_light_violation' "
                f"ORDER BY e.occurred_at DESC LIMIT {LIMIT};"
            )
            rows = [r for r in psql(sql).splitlines() if r.strip()]
    print(f"export feu {row_source}={len(rows)} since={SINCE or 'all'}", flush=True)

    cards: list[dict] = []
    for idx, line in enumerate(rows, 1):
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        aid, ats, snap_raw = parts[0], parts[1], parts[2]
        try:
            snap = json.loads(snap_raw) if snap_raw and snap_raw != "null" else {}
        except json.JSONDecodeError:
            snap = {}
        pkg = snap.get("package") or snap or {}
        meta = pkg.get("metadata") or {}
        payload = snap.get("payload") or meta.get("payload") or {}
        fe_id = str(meta.get("frigate_event_id") or payload.get("frigate_event_id") or "")
        folder = out_wsl / f"hit_{idx:02d}_{aid[:8]}"
        folder.mkdir(parents=True, exist_ok=True)

        media: dict[str, str] = {}
        for im in pkg.get("images") or []:
            role = str(im.get("role") or "image")
            asset_id = str(im.get("asset_id") or "")
            dest = folder / f"backend_{role}.jpg"
            if tok and download_backend_asset(tok, asset_id, dest):
                media[f"backend_{role}"] = str(dest.relative_to(out_wsl)).replace("\\", "/")

        frigate_ev: dict = {}
        if fe_id:
            try:
                frigate_ev = http_json(f"{FRIGATE}/api/events/{urllib.parse.quote(fe_id, safe='')}")
            except Exception as exc:
                frigate_ev = {"_fetch_error": str(exc)}
            for label, fname in (
                ("/snapshot.jpg", "frigate_snapshot.jpg"),
                ("/thumbnail.jpg", "frigate_thumbnail.jpg"),
            ):
                dest = folder / fname
                if download_frigate(f"/api/events/{fe_id}{label}", dest):
                    media[fname.replace(".jpg", "")] = str(dest.relative_to(out_wsl)).replace("\\", "/")

        poly = (
            meta.get("light_zone_polygon")
            or payload.get("light_zone_polygon")
            or (frigate_ev.get("data") or {}).get("light_zone_polygon")
            or []
        )
        if not isinstance(poly, list):
            poly = []
        if not poly:
            poly = light_polygon_from_db(str(meta.get("frigate_camera_id") or ""))
        obs_poly = obs_polygon_from_db(str(meta.get("frigate_camera_id") or ""))

        hsv_checks: dict[str, str | None] = {}
        for key, rel in media.items():
            if key == "backend_scene" or key == "frigate_snapshot":
                p = out_wsl / rel
                hsv_checks[key] = classify_scene_light(p, poly)

        # Gate: alert bbox centre must sit inside Zone_Observation (DB polygon,
        # read-only). None = polygon missing → fail-closed downstream.
        bbox_center_in_obs: bool | None = None
        nb = _norm_bbox(_parse_bbox(meta.get("bbox")))
        if nb and obs_poly:
            cx = nb["x"] + nb["width"] / 2.0
            cy = nb["y"] + nb["height"] / 2.0
            bbox_center_in_obs = point_in_polygon(cx, cy, obs_poly)

        scene_rel = media.get("backend_scene")
        if scene_rel:
            overlay_dest = folder / "scene_zones_overlay.jpg"
            if draw_zones_overlay(
                out_wsl / scene_rel, overlay_dest, poly, obs_poly,
                _parse_bbox(meta.get("bbox")),
            ):
                media["scene_zones_overlay"] = str(overlay_dest.relative_to(out_wsl)).replace("\\", "/")

        meta_out = {
            "alert_id": aid,
            "created_at": ats,
            "frigate_event_id": fe_id,
            "evidence_status": meta.get("evidence_status"),
            "capture_source": meta.get("capture_source"),
            "bbox_source": meta.get("bbox_source"),
            "scene_light_state": meta.get("scene_light_state"),
            "align_delta_ms": meta.get("align_delta_ms"),
            "capture_frame_ts": meta.get("capture_frame_ts"),
            "capture_frame_pts": meta.get("capture_frame_pts"),
            "bbox": meta.get("bbox"),
            "ia_bbox": meta.get("ia_bbox"),
            "subject_quality_ok": meta.get("subject_quality_ok"),
            "subject_texture": meta.get("subject_texture"),
            "abort_reason": meta.get("abort_reason"),
            "violation_status": meta.get("violation_status"),
            "frigate_camera_id": meta.get("frigate_camera_id"),
            "bbox_center_in_obs": bbox_center_in_obs,
            "hsv_recheck": hsv_checks,
            "frigate_event": {
                k: frigate_ev.get(k)
                for k in ("id", "camera", "label", "start_time", "end_time", "has_clip", "has_snapshot", "top_score")
                if frigate_ev.get(k) is not None
            },
            "frigate_data_bbox": (frigate_ev.get("data") or {}).get("box"),
        }
        gates_ok, gate_failures = evaluate_strict_gates(meta_out)
        meta_out["strict_gates_ok"] = gates_ok
        meta_out["strict_gate_failures"] = gate_failures
        (folder / "meta.json").write_text(json.dumps(meta_out, indent=2, ensure_ascii=False), encoding="utf-8")
        cards.append({"folder": folder.name, "media": media, "meta": meta_out})
        print(f"  hit#{idx} id={aid[:8]} fe={fe_id[:20] if fe_id else '-'} images={len(media)}", flush=True)

    cards.sort(key=lambda c: (not bool((c.get("meta") or {}).get("strict_gates_ok")), str((c.get("meta") or {}).get("created_at") or "")))
    overall_pass = bool(cards) and any(
        (c.get("meta") or {}).get("strict_gates_ok") for c in cards
    )

    summary = {
        "ts": TS,
        "since": SINCE,
        "rule": RULE_NAME,
        "hits": len(cards),
        "overall_pass": overall_pass,
        "items": cards,
    }
    (out_wsl / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    banner_class = "ok" if overall_pass else "bad"
    banner_text = "PASS — hit feu exploitable trouvé" if overall_pass else "FAIL — aucun hit feu exploitable"

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>1-hit feu rouge — {html.escape(TS)}</title>",
        "<style>",
        "body{font-family:Segoe UI,system-ui,sans-serif;margin:24px;background:#0f1115;color:#e8eaed}",
        "h1{font-size:1.45rem} h2{font-size:1.1rem;margin:24px 0 10px}",
        ".banner{padding:14px 18px;border-radius:10px;margin:0 0 20px;font-weight:600;font-size:1.05rem}",
        ".card{border:1px solid #2a2f3a;border-radius:12px;padding:16px;margin:0 0 24px;background:#171a21}",
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}",
        "img{max-width:100%;background:#000;border:1px solid #333;border-radius:8px}",
        ".tag{display:inline-block;padding:2px 8px;border-radius:999px;background:#2a3140;margin:0 6px 6px 0;font-size:12px}",
        ".ok{background:#1e3a2f;color:#8fd9a8}.bad{background:#3a1e1e;color:#f28b82}",
        "pre{background:#0a0c10;padding:10px;border-radius:8px;overflow:auto;font-size:12px}",
        ".caption{font-size:12px;color:#9aa0a6;margin:4px 0 8px}",
        ".audit{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin:10px 0}",
        ".audit div{background:#0a0c10;padding:8px 10px;border-radius:8px;font-size:12px}",
        "</style></head><body>",
        f"<div class='banner {banner_class}'>{html.escape(banner_text)}</div>",
        "<h1>1-hit feu rouge — revue preuves Frigate vs backend</h1>",
        f"<p>Run <code>{html.escape(TS)}</code> · since={html.escape(SINCE or 'all')}</p>",
        "<p>Critères PASS : <code>scene_light_state=red</code> · "
        "<code>hsv_recheck.backend_scene=red</code> · "
        "<code>bbox_source=frigate_mqtt</code> · <code>capture_source=frigate_track</code> · "
        "<code>bbox_center_in_obs=True</code> (centre bbox dans Zone_Observation) · "
        f"subject_texture≥{SUBJECT_TEXTURE_MIN}. "
        "<code>evidence_status=complete</code> reste informatif sauf si "
        "<code>FEU_1HIT_REQUIRE_COMPLETE=1</code>. "
        "L'image <code>scene_zones_overlay</code> montre les deux zones + bbox pour revue humaine.</p>",
    ]

    if not cards:
        blockers = fetch_blockers_summary()
        parts.append("<div class='card'><p><b>Aucune alerte feu exportée</b> pour cette fenêtre.</p>")
        parts.append("<h2>Blockers (dernier snapshot IA)</h2>")
        parts.append(
            f"<pre>{html.escape(json.dumps(blockers, indent=2, ensure_ascii=False, default=str))}</pre>"
        )
        parts.append("</div>")
    for card in cards:
        m = card["meta"]
        scene_meta = str(m.get("scene_light_state") or "?")
        hsv = m.get("hsv_recheck") or {}
        backend_hsv = hsv.get("backend_scene") or "?"
        gates_ok = bool(m.get("strict_gates_ok"))
        gate_failures = m.get("strict_gate_failures") or []
        vclass = "ok" if gates_ok else "bad"
        parts.append("<div class='card'>")
        parts.append(
            f"<h2>Alerte {html.escape(m.get('alert_id','')[:12])}</h2>"
            f"<span class='tag {vclass}'>{'STRICT PASS' if gates_ok else 'STRICT FAIL'}</span>"
            f"<span class='tag'>evidence={html.escape(str(m.get('evidence_status') or ''))}</span>"
            f"<span class='tag'>bbox_src={html.escape(str(m.get('bbox_source') or ''))}</span>"
            f"<span class='tag'>src={html.escape(str(m.get('capture_source') or ''))}</span>"
            f"<span class='tag'>scene_light={html.escape(scene_meta)}</span>"
            f"<span class='tag'>hsv_scene={html.escape(str(backend_hsv))}</span>"
            f"<span class='tag'>align_ms={html.escape(str(m.get('align_delta_ms') or ''))}</span>"
            f"<span class='tag'>texture={html.escape(str(m.get('subject_texture') or ''))}</span>"
        )
        if gate_failures:
            parts.append(
                f"<p class='caption bad'>Gates échoués : {html.escape('; '.join(gate_failures))}</p>"
            )
        parts.append(f"<p class='caption'>{html.escape(str(m.get('created_at') or ''))} · "
                     f"frigate_event={html.escape(str(m.get('frigate_event_id') or ''))}</p>")
        parts.append("<div class='audit'>")
        for label, key in (
            ("Evidence", "evidence_status"),
            ("Scene light", "scene_light_state"),
            ("Bbox source", "bbox_source"),
            ("Capture", "capture_source"),
            ("Subject OK", "subject_quality_ok"),
            ("Texture", "subject_texture"),
            ("Align ms", "align_delta_ms"),
            ("Capture frame", "capture_frame_ts"),
            ("Bbox in obs zone", "bbox_center_in_obs"),
            ("Abort", "abort_reason"),
        ):
            val = m.get(key)
            if val is not None and val != "":
                parts.append(f"<div><b>{html.escape(label)}</b><br>{html.escape(str(val))}</div>")
        parts.append("</div>")
        parts.append("<div class='grid'>")
        order = [
            "scene_zones_overlay", "backend_scene", "backend_subject",
            "frigate_snapshot", "frigate_thumbnail",
        ]
        media = card.get("media") or {}
        for key in order:
            rel = media.get(key)
            if not rel:
                continue
            hsv_val = hsv.get(key, "")
            cap = f"{key}" + (f" · HSV={hsv_val}" if hsv_val else "")
            parts.append(
                f"<div><div class='caption'>{html.escape(cap)}</div>"
                f"<img src='{html.escape(rel)}' alt='{html.escape(key)}'></div>"
            )
        parts.append("</div>")
        show = {
            k: m.get(k)
            for k in (
                "bbox", "ia_bbox", "bbox_source", "frigate_data_bbox",
                "subject_quality_ok", "subject_texture", "strict_gate_failures",
                "violation_status", "frigate_event", "hsv_recheck",
            )
            if m.get(k) is not None
        }
        parts.append(f"<pre>{html.escape(json.dumps(show, indent=2, ensure_ascii=False))}</pre>")
        parts.append("</div>")

    parts.append("<p><a href='summary.json'>summary.json</a></p></body></html>")
    (out_wsl / "index.html").write_text("\n".join(parts), encoding="utf-8")

    if out_win.resolve() != out_wsl.resolve():
        out_win.parent.mkdir(parents=True, exist_ok=True)
        if out_win.exists():
            shutil.rmtree(out_win)
        shutil.copytree(out_wsl, out_win)

    print(f"\nWSL_OUT={out_wsl}", flush=True)
    print(f"OVERALL_PASS={overall_pass}", flush=True)
    print(f"Open: C:\\Users\\gheno\\citevision\\validation-evidence\\1hit-feu-{TS}\\index.html", flush=True)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    os.chdir(str(ROOT))
    sys.path.insert(0, str(ROOT / "ai-engine" / "src"))
    raise SystemExit(main())
