#!/usr/bin/env python3
"""Galerie diagnostic 1-hit vitesse — preuves Frigate exit-only (pas de moteur local)."""
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
RULE_NAME = "Démo · Excès de vitesse"
LIMIT = max(1, int(os.environ.get("HIT1_EXPORT_LIMIT", "5") or 5))


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
        ],
        capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip()


def login() -> str | None:
    try:
        body = json.dumps({"email": EMAIL, "password": PASS}).encode()
        req = urllib.request.Request(
            f"{API}/api/v1/auth/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data.get("access_token") or data.get("token")
    except Exception as exc:
        print(f"login failed: {exc}", flush=True)
        return None


def download_backend_asset(tok: str, asset_id: str, dest: Path) -> bool:
    if not asset_id:
        return False
    key = urllib.parse.quote(asset_id, safe="")
    url = f"{API}/api/v1/orgs/{ORG}/evidence/asset?key={key}"
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if data and len(data) > 200:
            dest.write_bytes(data)
            return True
    except Exception as exc:
        print(f"  asset fail {asset_id[:48]}: {exc}", flush=True)
        return False
    return False


def download_frigate(path: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(f"{FRIGATE}{path}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if data and len(data) > 200:
            dest.write_bytes(data)
            return True
    except Exception as exc:
        print(f"  frigate fail {path}: {exc}", flush=True)
        return False
    return False


def speed_zone_from_db(frigate_camera_id: str) -> dict:
    """speed_measurement zone (polygon + config) for the camera — read-only."""
    cam = (frigate_camera_id or "").strip()
    if cam.startswith("cv_"):
        cam = cam[3:]
    if not cam:
        return {}
    sql = (
        "SELECT polygon::text, coalesce(behavior_config::text,'{}'), name FROM zones "
        f"WHERE org_id='{ORG}'::uuid AND camera_id='{cam}'::uuid "
        "AND behavior_config->>'behavior'='speed_measurement' AND is_active=true LIMIT 1;"
    )
    raw = psql(sql)
    if not raw:
        return {}
    parts = raw.split("|", 2)
    if len(parts) < 2:
        return {}
    try:
        poly = json.loads(parts[0]) if parts[0] else []
        bcfg = json.loads(parts[1]) if parts[1] else {}
    except json.JSONDecodeError:
        return {}
    return {
        "polygon": poly if isinstance(poly, list) else [],
        "config": (bcfg.get("config") or {}) if isinstance(bcfg, dict) else {},
        "name": parts[2] if len(parts) > 2 else "",
    }


def _norm_bbox(bbox) -> dict | None:
    if isinstance(bbox, str):
        try:
            bbox = json.loads(bbox)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(bbox, dict):
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


def draw_speed_zone_overlay(scene_path: Path, dest_path: Path, poly: list, bbox, label: str) -> bool:
    """Annotated scene: speed_measurement polygon + alert bbox for human review."""
    try:
        import cv2
        import numpy as np

        arr = np.fromfile(str(scene_path), dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return False
        h, w = frame.shape[:2]
        pts = []
        for p in poly or []:
            try:
                if isinstance(p, dict):
                    pts.append((float(p.get("x", 0)), float(p.get("y", 0))))
                elif isinstance(p, (list, tuple)) and len(p) >= 2:
                    pts.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError):
                continue
        if len(pts) >= 3:
            vals = [v for pt in pts for v in pt]
            scale = max(vals) <= 1.5
            px = np.array(
                [(int(x * w) if scale else int(x), int(y * h) if scale else int(y)) for x, y in pts],
                dtype=np.int32,
            )
            cv2.polylines(frame, [px], True, (0, 200, 255), 2)
            cv2.putText(frame, label or "speed_zone",
                        (int(px[:, 0].min()), max(18, int(px[:, 1].min()) - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)
        nb = _norm_bbox(bbox)
        if nb:
            x1, y1 = int(nb["x"] * w), int(nb["y"] * h)
            x2, y2 = int((nb["x"] + nb["width"]) * w), int((nb["y"] + nb["height"]) * h)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 60, 255), 2)
            cv2.putText(frame, "vehicle bbox", (x1, max(14, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 255), 2)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not ok:
            return False
        dest_path.write_bytes(buf.tobytes())
        return True
    except Exception as exc:
        print(f"  overlay skip: {exc}", flush=True)
        return False


def evaluate_speed_gates(meta: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    method = str(meta.get("detection_method") or "")
    emit_mode = str(meta.get("speed_emit_mode") or meta.get("zone_entry_exit") or "")
    bbox_src = str(meta.get("bbox_source") or "")
    evidence = str(meta.get("evidence_status") or "")
    speed = meta.get("speed_kmh")
    limit = meta.get("speed_limit_kmh")
    start_t = meta.get("frigate_start_time")
    end_t = meta.get("frigate_end_time")
    has_subject = bool(meta.get("has_subject"))
    has_scene = bool(meta.get("has_scene"))

    if method and method != "frigate_speed":
        failures.append(f"detection_method={method} (want frigate_speed)")
    if emit_mode and emit_mode not in ("exit",):
        failures.append(f"emit_mode={emit_mode} (want exit)")
    if bbox_src and "frigate" not in bbox_src.lower():
        failures.append(f"bbox_source={bbox_src}")
    if evidence and evidence not in ("complete", "partial"):
        failures.append(f"evidence_status={evidence}")
    try:
        if speed is not None and limit is not None and float(speed) < float(limit):
            failures.append(f"speed {speed} < limit {limit}")
    except (TypeError, ValueError):
        failures.append("speed/limit unreadable")
    if start_t is not None and end_t is not None:
        try:
            if float(end_t) <= float(start_t):
                failures.append("end_time <= start_time (no full traversal)")
        except (TypeError, ValueError):
            pass
    if not has_scene:
        failures.append("missing scene image")
    if not has_subject:
        failures.append("missing subject/bbox crop")
    # Process PASS: Frigate exit emit + images present (subject can be thumbnail).
    return (len(failures) == 0), failures


def main() -> int:
    if not TS:
        print("HIT1_TS required", flush=True)
        return 2
    out_wsl = ROOT / "validation-evidence" / f"1hit-vitesse-{TS}"
    out_win = Path("/mnt/c/Users/gheno/citevision/validation-evidence") / f"1hit-vitesse-{TS}"
    out_wsl.mkdir(parents=True, exist_ok=True)

    tok = login()
    since_clause = f"AND a.created_at >= '{SINCE}'::timestamptz" if SINCE else ""
    sql_alerts = (
        "SELECT a.id::text, a.created_at::text, coalesce(a.evidence_snapshot::text,'null') "
        f"FROM alerts a JOIN rules r ON r.id=a.rule_id "
        f"WHERE a.org_id='{ORG}'::uuid AND r.name='{RULE_NAME}' "
        f"{since_clause} "
        f"ORDER BY a.created_at DESC LIMIT {LIMIT};"
    )
    rows = [r for r in psql(sql_alerts).splitlines() if r.strip()]
    row_source = "alerts"
    if not rows:
        since_e = f"AND e.occurred_at >= '{SINCE}'::timestamptz" if SINCE else ""
        sql_ev = (
            "SELECT e.id::text, e.occurred_at::text, coalesce(e.evidence_snapshot::text,'null') "
            f"FROM events e WHERE e.org_id='{ORG}'::uuid "
            "AND e.event_type='speeding' "
            f"{since_e} "
            f"ORDER BY e.occurred_at DESC LIMIT {LIMIT};"
        )
        rows = [r for r in psql(sql_ev).splitlines() if r.strip()]
        row_source = "events"
    print(f"export vitesse {row_source}={len(rows)} since={SINCE or 'all'}", flush=True)

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
        meta = dict(pkg.get("metadata") or {})
        payload = snap.get("payload") or meta.get("payload") or {}
        for k in (
            "detection_method", "speed_emit_mode", "zone_entry_exit",
            "speed_kmh", "speed_limit_kmh", "speed_est_kmh",
            "frigate_start_time", "frigate_end_time", "bbox_source",
            "evidence_status", "frigate_event_id",
            "plate_number", "plate_confidence", "plate_ocr_source", "plate_status",
        ):
            if meta.get(k) is None:
                meta[k] = payload.get(k) or snap.get(k)
        if meta.get("speed_kmh") is None:
            meta["speed_kmh"] = snap.get("speed_kmh") or payload.get("speed_kmh")
        if meta.get("speed_limit_kmh") is None:
            meta["speed_limit_kmh"] = snap.get("speed_limit_kmh") or payload.get("speed_limit_kmh")
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
                with urllib.request.urlopen(
                    f"{FRIGATE}/api/events/{urllib.parse.quote(fe_id, safe='')}", timeout=20
                ) as resp:
                    frigate_ev = json.loads(resp.read().decode())
            except Exception as exc:
                frigate_ev = {"_fetch_error": str(exc)}
            for label, fname in (
                ("/snapshot.jpg", "frigate_snapshot.jpg"),
                ("/thumbnail.jpg", "frigate_thumbnail.jpg"),
            ):
                dest = folder / fname
                if download_frigate(f"/api/events/{fe_id}{label}", dest):
                    media[fname.replace(".jpg", "")] = str(dest.relative_to(out_wsl)).replace("\\", "/")
            if meta.get("frigate_start_time") is None:
                meta["frigate_start_time"] = frigate_ev.get("start_time")
            if meta.get("frigate_end_time") is None:
                meta["frigate_end_time"] = frigate_ev.get("end_time")

        # Annotated scene: speed zone polygon + Frigate bbox at zone exit.
        scene_rel = media.get("backend_scene") or media.get("frigate_snapshot")
        if scene_rel:
            cam_ref = str(
                frigate_ev.get("camera")
                or payload.get("camera_id") or meta.get("camera_id")
                or snap.get("camera_id") or ""
            )
            zone = speed_zone_from_db(cam_ref)
            label = (
                f"{zone.get('name') or 'speed_zone'} "
                f"{meta.get('speed_kmh')} km/h / limit {meta.get('speed_limit_kmh')}"
            )
            overlay_dest = folder / "scene_zones_overlay.jpg"
            if draw_speed_zone_overlay(
                out_wsl / scene_rel, overlay_dest, zone.get("polygon") or [],
                meta.get("bbox") or payload.get("bbox") or snap.get("bbox"), label,
            ):
                media["scene_zones_overlay"] = str(overlay_dest.relative_to(out_wsl)).replace("\\", "/")

        meta["has_scene"] = bool(media.get("backend_scene") or media.get("frigate_snapshot"))
        meta["has_subject"] = bool(media.get("backend_subject") or media.get("frigate_thumbnail"))
        gates_ok, gate_failures = evaluate_speed_gates(meta)
        meta_out = {
            **{k: meta.get(k) for k in (
                "detection_method", "speed_emit_mode", "zone_entry_exit",
                "speed_kmh", "speed_limit_kmh", "bbox_source", "evidence_status",
                "frigate_event_id", "frigate_start_time", "frigate_end_time",
                "has_scene", "has_subject", "bbox",
                "plate_number", "plate_confidence", "plate_ocr_source", "plate_status",
            )},
            "alert_id": aid,
            "created_at": ats,
            "strict_gates_ok": gates_ok,
            "strict_gate_failures": gate_failures,
            "frigate_event": {
                k: frigate_ev.get(k)
                for k in ("id", "camera", "label", "start_time", "end_time", "has_clip", "has_snapshot")
                if frigate_ev.get(k) is not None
            },
        }
        (folder / "meta.json").write_text(json.dumps(meta_out, indent=2, ensure_ascii=False), encoding="utf-8")
        cards.append({"folder": folder.name, "media": media, "meta": meta_out})
        print(
            f"  hit#{idx} id={aid[:8]} speed={meta.get('speed_kmh')} "
            f"limit={meta.get('speed_limit_kmh')} mode={meta.get('speed_emit_mode')} "
            f"images={len(media)} pass={gates_ok}",
            flush=True,
        )

    overall_pass = bool(cards) and any((c.get("meta") or {}).get("strict_gates_ok") for c in cards)
    summary = {
        "ts": TS,
        "since": SINCE,
        "rule": RULE_NAME,
        "hits": len(cards),
        "overall_pass": overall_pass,
        "items": cards,
    }
    (out_wsl / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    banner = "PASS — hit vitesse Frigate exit exploitable" if overall_pass else "FAIL — aucun hit vitesse exploitable"
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>1-hit vitesse — {html.escape(TS)}</title>",
        "<style>",
        "body{font-family:Segoe UI,system-ui,sans-serif;margin:24px;background:#0f1115;color:#e8eaed}",
        ".banner{padding:14px 18px;border-radius:10px;margin:0 0 20px;font-weight:600}",
        ".ok{background:#1e3a2f;color:#8fd9a8}.bad{background:#3a1e1e;color:#f28b82}",
        ".card{border:1px solid #2a2f3a;border-radius:12px;padding:16px;margin:0 0 24px;background:#171a21}",
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}",
        "img{max-width:100%;border-radius:8px;border:1px solid #333}",
        ".tag{display:inline-block;padding:2px 8px;border-radius:999px;background:#2a3140;margin:0 6px 6px 0;font-size:12px}",
        "pre{white-space:pre-wrap;background:#0c0e12;padding:10px;border-radius:8px;font-size:12px}",
        "</style></head><body>",
        f"<h1>1-hit vitesse Frigate — {html.escape(TS)}</h1>",
        f"<div class='banner {'ok' if overall_pass else 'bad'}'>{html.escape(banner)}</div>",
        f"<p>hits={len(cards)} since={html.escape(SINCE or 'all')} "
        f"source={html.escape(row_source)} detection=frigate_speed emit=exit</p>",
    ]
    for c in cards:
        m = c.get("meta") or {}
        media = c.get("media") or {}
        ok = bool(m.get("strict_gates_ok"))
        parts.append("<div class='card'>")
        parts.append(f"<h2>{html.escape(c.get('folder') or '')} "
                     f"<span class='tag {'ok' if ok else 'bad'}'>{'PASS' if ok else 'FAIL'}</span></h2>")
        for key in (
            "speed_kmh", "speed_limit_kmh", "speed_emit_mode", "detection_method",
            "bbox_source", "evidence_status", "frigate_event_id",
            "frigate_start_time", "frigate_end_time",
            "plate_number", "plate_confidence", "plate_ocr_source", "plate_status",
        ):
            parts.append(f"<span class='tag'>{html.escape(key)}={html.escape(str(m.get(key)))}</span>")
        fails = m.get("strict_gate_failures") or []
        if fails:
            parts.append("<pre>" + html.escape("\n".join(str(f) for f in fails)) + "</pre>")
        parts.append("<div class='grid'>")
        for label, rel in media.items():
            parts.append(
                f"<div><div class='tag'>{html.escape(label)}</div>"
                f"<img src='{html.escape(rel)}' alt='{html.escape(label)}'></div>"
            )
        parts.append("</div></div>")
    parts.append("</body></html>")
    (out_wsl / "index.html").write_text("\n".join(parts), encoding="utf-8")

    try:
        out_win.parent.mkdir(parents=True, exist_ok=True)
        if out_win.exists():
            shutil.rmtree(out_win, ignore_errors=True)
        shutil.copytree(out_wsl, out_win)
    except Exception as exc:
        print(f"win copy warn: {exc}", flush=True)

    print(f"OVERALL_PASS={overall_pass}", flush=True)
    print(f"GALLERY={out_wsl / 'index.html'}", flush=True)
    print(f"GALLERY_WIN={out_win / 'index.html'}", flush=True)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
