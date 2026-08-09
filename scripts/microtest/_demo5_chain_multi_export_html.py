#!/usr/bin/env python3
"""Export chain-multi evidence gallery: VLM-first cabin + zone/bbox overlays."""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("MICROTEST_ROOT", Path.home() / "citevision-v2"))
ORG = os.environ.get("DEMO_ORG_ID") or os.environ.get("DEFAULT_ORG_ID") or ""
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081").rstrip("/")
AI = os.environ.get("AI_URL", "http://127.0.0.1:8001").rstrip("/")
FRIGATE = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
GO2RTC = os.environ.get("GO2RTC_URL", "http://127.0.0.1:1984").rstrip("/")
MAILHOG = os.environ.get("MAILHOG_URL", "http://127.0.0.1:8025").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
TS = (
    os.environ.get("CHAIN_MULTI_TS")
    or os.environ.get("CHAIN_SMOKE_TS")
    or os.environ.get("DEMO5_TS")
    or os.environ.get("TS")
    or ""
)
RESULTS_JSON = Path(
    os.environ.get("CHAIN_MULTI_RESULTS_JSON")
    or os.environ.get("CHAIN_SMOKE_RESULTS_JSON")
    or (ROOT / "logs" / f"chain-multi-results-{TS}.json")
)

RULES = [
    ("comptage", "Démo · Comptage véhicules", ["line_cross", "vehicle_count_threshold", "vehicle_corridor", "zone_count"]),
    ("vitesse", "Démo · Excès de vitesse", ["speeding"]),
    ("feu", "Démo · Feu rouge", ["red_light_violation"]),
    ("ceinture", "Démo · Non-port ceinture", ["seatbelt_violation", "seatbelt"]),
    ("telephone", "Démo · Téléphone au volant", ["phone_use_violation"]),
]

VIDEO_LABEL = {
    "comptage": "Décompte",
    "vitesse": "Ligne Continue",
    "feu": "Feux",
    "ceinture": "Port de Ceinture",
    "telephone": "Port de Ceinture",
}

VLM_NAME_FILTER = {
    "feu": ("red_light", "feu"),
    "ceinture": ("seatbelt", "ceinture"),
    "telephone": ("phone_use", "phone", "telephone"),
}

ROLE_LABEL = {
    "scene": "Scene",
    "scene_zones": "Scene + zones",
    "crop": "Crop",
    "crop_zones": "Crop + zones",
    "subject": "Sujet",
    "plate": "Plaque",
    "Crop VLM": "Crop VLM",
}


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


def http_json(url: str, timeout: float = 8.0) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except Exception:
        return {}


def req(method: str, url: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def download_asset(token: str, asset_id: str, dest: Path) -> bool:
    if not asset_id or not ORG:
        return False
    key = urllib.parse.quote(asset_id, safe="")
    url = f"{API}/api/v1/orgs/{ORG}/evidence/asset?key={key}"
    try:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=120) as resp:
            data = resp.read()
        if not data or len(data) < 200:
            return False
        dest.write_bytes(data)
        return True
    except Exception as exc:
        print(f"  asset fail {asset_id[:48]}: {exc}", flush=True)
        return False


def download_frigate(path: str, dest: Path) -> bool:
    url = f"{FRIGATE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
        if not data or len(data) < 200:
            return False
        dest.write_bytes(data)
        return True
    except Exception as exc:
        print(f"  frigate fail {path}: {exc}", flush=True)
        return False


def resolve_org() -> str:
    global ORG
    if ORG:
        return ORG
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("DEFAULT_ORG_ID="):
                ORG = line.split("=", 1)[1].strip()
                if ORG:
                    return ORG
    ORG = psql(
        "SELECT org_id::text FROM org_demo_settings ORDER BY updated_at DESC NULLS LAST LIMIT 1;"
    ).strip()
    return ORG


def fetch_zones_db() -> list[dict]:
    """Read-only zones from Postgres when API login fails."""
    if not ORG:
        return []
    raw = psql(
        "SELECT coalesce(name,''), coalesce(camera_id::text,''), "
        "coalesce(polygon::text,'[]'), coalesce(behavior_config::text,'{}') "
        f"FROM zones WHERE org_id='{ORG}'::uuid AND coalesce(is_active,true)=true;"
    )
    out: list[dict] = []
    for line in (raw or "").splitlines():
        parts = line.split("|", 3)
        if len(parts) < 3:
            continue
        try:
            poly = json.loads(parts[2]) if parts[2] else []
        except json.JSONDecodeError:
            poly = []
        out.append({
            "name": parts[0],
            "zone_id": parts[0],
            "camera_id": parts[1],
            "polygon": poly if isinstance(poly, list) else [],
        })
    return out


def fetch_zones(token: str) -> list[dict]:
    if token and ORG:
        try:
            raw = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token)
            if isinstance(raw, dict):
                raw = raw.get("items") or raw.get("zones") or raw.get("data") or []
            if isinstance(raw, list) and raw:
                return list(raw)
        except Exception as exc:
            print(f"  zones API fail: {exc}", flush=True)
    dbz = fetch_zones_db()
    if dbz:
        print(f"  zones from DB fallback count={len(dbz)}", flush=True)
    return dbz


def zones_for_camera(zones: list[dict], camera_id: str) -> list[dict]:
    cam = (camera_id or "").strip()
    if cam.startswith("cv_"):
        cam = cam[3:]
    out = []
    for z in zones:
        zc = str(z.get("camera_id") or "").strip()
        if zc.startswith("cv_"):
            zc = zc[3:]
        if cam and zc and zc != cam:
            continue
        out.append(z)
    return out


def _poly_points(poly: list) -> list[tuple[float, float]]:
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
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _bbox_dict(bbox) -> dict | None:
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
    return {
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "norm": bool(bbox.get("norm")) or max(x, y, w, h) <= 1.5,
    }


def draw_zone_bbox_overlay(
    src: Path,
    dest: Path,
    zones: list[dict],
    bbox,
    legend: str,
    highlight_names: set[str] | None = None,
) -> tuple[bool, dict]:
    """Annotate image with zone polygons + bbox (Pillow). Returns (ok, info)."""
    info: dict = {"inside_zone": None, "zone_drawn": 0, "bbox_px": None}
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        print(f"  pillow missing: {exc}", flush=True)
        return False, info
    try:
        im = Image.open(src).convert("RGB")
    except Exception as exc:
        print(f"  open fail {src.name}: {exc}", flush=True)
        return False, info
    w, h = im.size
    draw = ImageDraw.Draw(im, "RGBA")
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    highlight_names = {n.lower() for n in (highlight_names or set())}
    bb = _bbox_dict(bbox)
    cx = cy = None
    if bb:
        if bb["norm"]:
            x1, y1 = bb["x"] * w, bb["y"] * h
            x2, y2 = (bb["x"] + bb["width"]) * w, (bb["y"] + bb["height"]) * h
        else:
            # Pixel bbox — scale if it looks like a different frame size.
            sx = sy = 1.0
            if bb["x"] + bb["width"] > w * 1.2 or bb["y"] + bb["height"] > h * 1.2:
                # assume 1920x1080 source coords
                sx, sy = w / 1920.0, h / 1080.0
            x1, y1 = bb["x"] * sx, bb["y"] * sy
            x2, y2 = (bb["x"] + bb["width"]) * sx, (bb["y"] + bb["height"]) * sy
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        info["bbox_px"] = {
            "x": int(x1), "y": int(y1),
            "width": int(x2 - x1), "height": int(y2 - y1),
        }
        draw.rectangle([x1, y1, x2, y2], outline=(220, 60, 60, 255), width=3)

    inside_any = None
    for z in zones:
        name = str(z.get("name") or z.get("zone_id") or "")
        poly = z.get("polygon") or z.get("points") or []
        pts = _poly_points(poly)
        if len(pts) < 3:
            continue
        vals = [v for pt in pts for v in pt]
        scale = max(vals) <= 1.5
        px = [
            (int(x * w) if scale else int(x), int(y * h) if scale else int(y))
            for x, y in pts
        ]
        is_hi = name.lower() in highlight_names if highlight_names else False
        color = (0, 220, 140, 220) if is_hi else (0, 170, 255, 180)
        width = 4 if is_hi else 2
        draw.line(px + [px[0]], fill=color, width=width)
        label_xy = (px[0][0] + 2, max(2, px[0][1] - 12))
        draw.text(label_xy, name[:28], fill=color[:3], font=font)
        info["zone_drawn"] = int(info["zone_drawn"]) + 1
        if cx is not None:
            # point_in_polygon uses same coordinate space as poly (norm or px)
            if scale:
                pin = point_in_polygon(cx / w, cy / h, poly)
            else:
                pin = point_in_polygon(cx, cy, poly)
            if pin is True:
                inside_any = True
            elif pin is False and inside_any is not True:
                inside_any = False if is_hi or inside_any is None else inside_any

    if highlight_names and cx is not None:
        # Prefer inside check against highlighted zone(s) only.
        inside_hi = None
        for z in zones:
            name = str(z.get("name") or z.get("zone_id") or "")
            if name.lower() not in highlight_names:
                continue
            poly = z.get("polygon") or []
            pts = _poly_points(poly)
            if len(pts) < 3:
                continue
            scale = max(v for pt in pts for v in pt) <= 1.5
            if scale:
                pin = point_in_polygon(cx / w, cy / h, poly)
            else:
                pin = point_in_polygon(cx, cy, poly)
            if pin is True:
                inside_hi = True
                break
            if pin is False:
                inside_hi = False
        if inside_hi is not None:
            inside_any = inside_hi

    info["inside_zone"] = inside_any
    legend_bits = [legend or ""]
    if info["inside_zone"] is True:
        legend_bits.append("inside=yes")
    elif info["inside_zone"] is False:
        legend_bits.append("inside=no")
    legend_bits.append("crop_mode=frigate_vehicle_bbox")
    text = " | ".join(b for b in legend_bits if b)
    draw.rectangle([0, h - 22, w, h], fill=(10, 14, 20, 200))
    draw.text((6, h - 18), text[:110], fill=(240, 240, 240), font=font)
    try:
        im.save(dest, format="JPEG", quality=88)
        return True, info
    except Exception as exc:
        print(f"  save overlay fail: {exc}", flush=True)
        return False, info


def collect_vlm_crops(out: Path, slug: str, max_n: int = 3) -> list[dict]:
    """Attach newest VLM dumps for the rule (cabin: prefer over stale live alerts)."""
    media_items: list[dict] = []
    needles = VLM_NAME_FILTER.get(slug) or ()
    if not needles:
        return media_items
    dump_roots = sorted(
        [p for p in ROOT.glob("validation-evidence/vlm-cabin-*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not dump_roots:
        return media_items
    # Prefer newest dump dirs that contain matching files
    matched: list[Path] = []
    for src in dump_roots[:6]:
        jpgs = [
            p for p in sorted(src.rglob("*.jpg"), reverse=True)
            if any(n in p.name.lower() for n in needles)
            and ("_crop" in p.name.lower() or "_no_crop" in p.name.lower() or "crop" in p.name.lower())
        ]
        # Prefer real crop files over _no_crop when both exist
        crops = [p for p in jpgs if "_crop" in p.name.lower() and "_no_crop" not in p.name.lower()]
        picks = crops or jpgs
        for p in picks:
            if p not in matched:
                matched.append(p)
            if len(matched) >= max_n:
                break
        if len(matched) >= max_n:
            break
    dest_dir = out / slug / "vlm_dump"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p in matched[:max_n]:
        target = dest_dir / p.name
        try:
            shutil.copy2(p, target)
        except Exception:
            continue
        meta = {
            "note": "VLM dump du run (prioritaire cabine)",
            "capture_source": "vlm_dump",
            "crop_mode": "frigate_vehicle_bbox",
            "source_file": p.name,
        }
        stem = p.name
        for suf in ("_crop.jpg", "_no_crop.jpg", ".jpg"):
            if stem.endswith(suf):
                stem = stem[: -len(suf)]
                break
        for c in sorted(p.parent.glob(stem + "*.json"))[:1]:
            try:
                shutil.copy2(c, dest_dir / c.name)
                verdict = json.loads(c.read_text(encoding="utf-8", errors="replace"))
                for k in (
                    "zone_id", "bbox", "camera_id", "frigate_event_id",
                    "rule", "outcome", "reason_short", "confidence",
                ):
                    if k in verdict:
                        meta[k] = verdict[k]
            except Exception:
                pass
        media_items.append({
            "role": "crop",
            "path": str(target.relative_to(out)).replace("\\", "/"),
            "kind": "image",
            "meta": meta,
            "abs": target,
        })
    return media_items


def distinct_speed_ids_since(rule_id: str, since: str) -> list[str]:
    if not rule_id or not since:
        return []
    raw = psql(
        "SELECT DISTINCT coalesce("
        "a.evidence_snapshot->'package'->'metadata'->>'frigate_event_id', "
        "a.evidence_snapshot->'package'->'metadata'->>'frigate_id', "
        "a.id::text) "
        f"FROM alerts a WHERE a.org_id='{ORG}'::uuid "
        f"AND a.rule_id='{rule_id}'::uuid AND a.created_at>='{since}'::timestamptz "
        "AND coalesce(a.evidence_snapshot->'package'->'metadata'->>'capture_source','') "
        "IN ('frigate_track','frigate');"
    )
    return [x.strip() for x in (raw or "").splitlines() if x.strip()]


def collect_diagnostics(step_results: list[dict], extra: dict | None = None) -> dict:
    ai = http_json(f"{AI}/health")
    blockers = http_json(f"{AI}/debug/rule-blockers")
    frig_ver = ""
    try:
        with urllib.request.urlopen(f"{FRIGATE}/api/version", timeout=5) as r:
            frig_ver = r.read().decode().strip()
    except Exception:
        frig_ver = ""
    frig_cfg = http_json(f"{FRIGATE}/api/config")
    cams = len((frig_cfg or {}).get("cameras") or {})
    if cams < 1:
        stats = http_json(f"{FRIGATE}/api/stats")
        cams = len((stats or {}).get("cameras") or {})
    streams = 0
    try:
        st = http_json(f"{GO2RTC}/api/streams")
        streams = len(st) if isinstance(st, dict) else 0
    except Exception:
        streams = 0
    mailhog_ok = False
    mail_count = 0
    try:
        with urllib.request.urlopen(f"{MAILHOG}/", timeout=5) as r:
            mailhog_ok = r.status == 200
        mh = http_json(f"{MAILHOG}/api/v2/messages?limit=5")
        mail_count = int((mh or {}).get("total") or 0)
    except Exception:
        pass

    vq = (blockers or {}).get("vlm_queue") or {}
    fb = (blockers or {}).get("frigate_bridge") or {}
    reject_top = (blockers or {}).get("vlm_reject_reason_top") or {}

    return {
        "ai_health": {
            "gemini_configured": ai.get("gemini_configured", ai.get("gemini_enabled")),
            "gemini_reachable": ai.get("gemini_reachable"),
            "gemini_model": ai.get("gemini_model"),
            "gpu_active": ai.get("gpu_active") or ai.get("yolo_cuda"),
            "frigate_vlm_bridge": ai.get("frigate_vlm_bridge"),
            "frigate_speed_bridge": ai.get("frigate_speed_bridge"),
            "frigate_geometry_bridge": ai.get("frigate_geometry_bridge"),
            "yolo_provider": ai.get("yolo_provider"),
        },
        "frigate": {"version": frig_ver, "cameras": cams},
        "go2rtc_streams": streams,
        "mailhog": {"ui_ok": mailhog_ok, "messages_total": mail_count},
        "vlm_queue": {
            "enqueued": vq.get("enqueued"),
            "completed": vq.get("completed"),
            "emitted": vq.get("emitted"),
            "rejected": vq.get("rejected"),
            "unclear": vq.get("unclear"),
            "reject_reason_top": reject_top,
        },
        "frigate_bridge_counters": {
            k: fb.get(k)
            for k in (
                "cabin_enqueued",
                "cabin_snapshot_fail",
                "speed_emitted",
                "geometry_emitted",
                "red_light_enqueued",
                "red_light_skipped_not_red",
                "red_light_skipped_unknown",
                "dropped_dedupe",
            )
        },
        "step_timings": [
            {"alias": s.get("alias"), "status": s.get("status"), "elapsed_sec": s.get("elapsed_sec")}
            for s in step_results
        ],
        **(extra or {}),
    }


def _human_role(role: str) -> str:
    return ROLE_LABEL.get(str(role or "image"), str(role or "image").replace("_", " ").capitalize())


def _render_kv_table(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    parts = ["<table class='kv'>"]
    for k, v in rows:
        parts.append(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>")
    parts.append("</table>")
    return "\n".join(parts)


def _render_diag_cards(diag: dict) -> str:
    ai = diag.get("ai_health") or {}
    frig = diag.get("frigate") or {}
    mh = diag.get("mailhog") or {}
    vq = diag.get("vlm_queue") or {}
    fb = diag.get("frigate_bridge_counters") or {}
    blocks = [
        (
            "AI / Gemini",
            [
                ("GPU", ai.get("gpu_active")),
                ("Provider", ai.get("yolo_provider")),
                ("Gemini configure", ai.get("gemini_configured")),
                ("Modele", ai.get("gemini_model")),
                ("Bridge VLM", ai.get("frigate_vlm_bridge")),
                ("Bridge speed", ai.get("frigate_speed_bridge")),
            ],
        ),
        (
            "Frigate / go2rtc",
            [
                ("Version", frig.get("version")),
                ("Cameras", frig.get("cameras")),
                ("Streams go2rtc", diag.get("go2rtc_streams")),
            ],
        ),
        (
            "VLM / cabin / feu",
            [
                ("VLM enqueued", vq.get("enqueued")),
                ("VLM completed", vq.get("completed")),
                ("VLM emitted", vq.get("emitted")),
                ("VLM rejected", vq.get("rejected")),
                ("Cabin enqueued", fb.get("cabin_enqueued")),
                ("Red light enqueued", fb.get("red_light_enqueued")),
                ("Red skip not_red", fb.get("red_light_skipped_not_red")),
                ("Red skip unknown", fb.get("red_light_skipped_unknown")),
            ],
        ),
        (
            "Vitesse distincte",
            [
                ("Distinct frigate IDs", len(diag.get("distinct_speed_ids") or [])),
                ("IDs", ", ".join((diag.get("distinct_speed_ids") or [])[:6]) or None),
            ],
        ),
        (
            "MailHog",
            [
                ("UI", "ok" if mh.get("ui_ok") else "down"),
                ("Messages", mh.get("messages_total")),
            ],
        ),
    ]
    out = ['<div class="diag-grid">']
    for title, rows in blocks:
        clean = [(k, v) for k, v in rows if v is not None and v != ""]
        out.append('<div class="card diag">')
        out.append(f"<h3>{html.escape(title)}</h3>")
        out.append(_render_kv_table([(k, str(v)) for k, v in clean]))
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


def annotate_media(
    out: Path,
    folder: Path,
    media: list[dict],
    zones: list[dict],
    meta: dict,
    slug: str,
) -> list[dict]:
    """Add scene_zones / crop_zones overlays next to existing media."""
    result = list(media)
    cam = str(meta.get("camera_id") or "")
    zid = str(meta.get("zone_id") or "")
    bbox = meta.get("bbox")
    fe = str(meta.get("frigate_event_id") or "")
    cam_zones = zones_for_camera(zones, cam) if cam else zones
    highlight = {zid} if zid else set()

    # Ensure a scene from Frigate when possible (for zone overlays).
    scene_path: Path | None = None
    for m in media:
        if m.get("role") in ("scene",) and m.get("abs"):
            scene_path = Path(m["abs"])
            break
        if m.get("role") in ("scene",) and m.get("path"):
            scene_path = out / m["path"]
            break
    if scene_path is None and fe:
        dest = folder / "scene.jpg"
        if download_frigate(f"/api/events/{urllib.parse.quote(fe, safe='')}/snapshot.jpg", dest):
            rel = str(dest.relative_to(out)).replace("\\", "/")
            result.insert(0, {"role": "scene", "path": rel, "kind": "image", "abs": dest})
            scene_path = dest

    legend = f"{slug} zone={zid or '?'}"
    if scene_path and scene_path.exists():
        ov = folder / "scene_zones.jpg"
        ok, info = draw_zone_bbox_overlay(
            scene_path, ov, cam_zones, bbox, legend, highlight_names=highlight,
        )
        if ok:
            rel = str(ov.relative_to(out)).replace("\\", "/")
            result.append({"role": "scene_zones", "path": rel, "kind": "image"})
            if info.get("inside_zone") is not None:
                meta["inside_zone"] = "yes" if info["inside_zone"] else "no"
            if info.get("bbox_px"):
                meta["bbox_px"] = info["bbox_px"]

    # Crop overlays (cabin dumps / subject)
    for m in list(media):
        role = str(m.get("role") or "")
        if role not in ("crop", "Crop VLM", "subject", "subject_asset_id"):
            continue
        src = Path(m["abs"]) if m.get("abs") else (out / m["path"] if m.get("path") else None)
        if not src or not src.exists():
            continue
        ov = folder / f"{src.stem}_zones.jpg"
        # On a crop image, zone polygon may be out of frame — still draw if coords fit.
        ok, info = draw_zone_bbox_overlay(
            src, ov, cam_zones if role == "subject" else [], bbox if role == "subject" else None,
            legend + " | crop", highlight_names=highlight,
        )
        if ok:
            rel = str(ov.relative_to(out)).replace("\\", "/")
            result.append({"role": "crop_zones", "path": rel, "kind": "image"})
            if info.get("inside_zone") is not None and meta.get("inside_zone") is None:
                meta["inside_zone"] = "yes" if info["inside_zone"] else "no"
        # Always compute inside_zone against scene-sized coords when we have zone+bbox
        if meta.get("inside_zone") is None and bbox and zid:
            for z in cam_zones:
                if str(z.get("name") or "").lower() != zid.lower():
                    continue
                bb = _bbox_dict(bbox)
                if not bb:
                    break
                poly = z.get("polygon") or []
                pts = _poly_points(poly)
                if len(pts) < 3:
                    break
                scale = max(v for pt in pts for v in pt) <= 1.5
                if bb["norm"]:
                    cx = bb["x"] + bb["width"] / 2
                    cy = bb["y"] + bb["height"] / 2
                    pin = point_in_polygon(cx, cy, poly) if scale else None
                else:
                    cx = bb["x"] + bb["width"] / 2
                    cy = bb["y"] + bb["height"] / 2
                    if scale:
                        # assume 1920x1080 for pixel→norm
                        pin = point_in_polygon(cx / 1920.0, cy / 1080.0, poly)
                    else:
                        pin = point_in_polygon(cx, cy, poly)
                if pin is not None:
                    meta["inside_zone"] = "yes" if pin else "no"
                break
    meta.setdefault("crop_mode", "frigate_vehicle_bbox")
    if zid:
        meta.setdefault("zone_id", zid)
    return result


def main() -> int:
    if not TS:
        print("CHAIN_MULTI_TS / TS required", file=sys.stderr)
        return 1
    resolve_org()
    if not ORG:
        print("ORG unresolved", file=sys.stderr)
        return 1

    out_wsl = ROOT / "validation-evidence" / f"chain-multi-{TS}"
    out_win = Path("/mnt/c/Users/gheno/citevision/validation-evidence") / f"chain-multi-{TS}"
    out_wsl.mkdir(parents=True, exist_ok=True)

    step_results: list[dict] = []
    if RESULTS_JSON.exists():
        try:
            step_results = list(json.loads(RESULTS_JSON.read_text(encoding="utf-8")).get("steps") or [])
        except Exception:
            step_results = []
    by_alias = {s.get("alias"): s for s in step_results}

    try:
        login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
        tok = login["access_token"]
    except Exception as exc:
        print(f"login fail: {exc}", flush=True)
        tok = ""

    zones = fetch_zones(tok) if tok else []
    print(f"zones_loaded={len(zones)}", flush=True)

    cards: list[dict] = []
    summary: dict = {"ts": TS, "org_id": ORG, "campaign": "chain-multi", "rules": [], "steps": step_results}
    distinct_speed: list[str] = []
    campaign_since = ""
    # Approximate since = start of campaign from first step log timestamp in results
    if TS:
        # TS is UTC compact; postgres timestamptz accept ISO
        campaign_since = (
            f"{TS[0:4]}-{TS[4:6]}-{TS[6:8]}T{TS[9:11]}:{TS[11:13]}:{TS[13:15]}Z"
            if len(TS) >= 15 else ""
        )

    for slug, rule_name, event_types in RULES:
        esc = rule_name.replace("'", "''")
        rule_row = psql(
            f"SELECT id::text FROM rules WHERE org_id='{ORG}'::uuid "
            f"AND name='{esc}' LIMIT 1;"
        )
        print(f"\n=== export {slug} rule={rule_name} ===", flush=True)
        rule_summary: dict = {
            "slug": slug,
            "rule": rule_name,
            "step": by_alias.get(slug) or {},
            "hits": 0,
            "items": [],
        }

        # Cabin / feu: ALWAYS prefer VLM dumps of the run (max 3) — never stale live alerts first.
        if slug in ("ceinture", "telephone", "feu"):
            max_n = 3 if slug in ("ceinture", "telephone") else 2
            vlm_media = collect_vlm_crops(out_wsl, slug, max_n=max_n)
            if vlm_media:
                # One card per crop for clarity
                for idx, m in enumerate(vlm_media, 1):
                    meta = dict(m.get("meta") or {})
                    folder = out_wsl / slug / f"vlm_{idx:02d}"
                    folder.mkdir(parents=True, exist_ok=True)
                    # move/copy crop into folder for overlays
                    src = Path(m["abs"])
                    local = folder / src.name
                    if src.resolve() != local.resolve():
                        try:
                            shutil.copy2(src, local)
                        except Exception:
                            local = src
                    m_local = {
                        "role": "crop",
                        "path": str(local.relative_to(out_wsl)).replace("\\", "/"),
                        "kind": "image",
                        "abs": local,
                    }
                    media = annotate_media(
                        out_wsl, folder, [m_local], zones, meta, slug,
                    )
                    # strip abs for JSON
                    media_out = [{k: v for k, v in x.items() if k != "abs"} for x in media]
                    item = {
                        "id": f"vlm-{idx}",
                        "ts": TS,
                        "status": meta.get("outcome") or "pipeline",
                        "capture_source": "vlm_dump",
                        "frigate_event_id": meta.get("frigate_event_id"),
                        "media": media_out,
                        "meta": {
                            **{k: meta.get(k) for k in (
                                "zone_id", "crop_mode", "inside_zone", "bbox", "bbox_px",
                                "camera_id", "outcome", "reason_short", "confidence", "note",
                            ) if meta.get(k) is not None},
                            "capture_source": "vlm_dump",
                        },
                    }
                    rule_summary["items"].append(item)
                    cards.append({"slug": slug, "rule": rule_name, **item})
                    print(
                        f"  {slug}#vlm{idx} zone={meta.get('zone_id')} "
                        f"inside={meta.get('inside_zone')} images={len(media_out)}",
                        flush=True,
                    )
            rule_summary["hits"] = len(rule_summary["items"])
            summary["rules"].append(rule_summary)
            continue

        # Road rules: export recent alerts (multi for vitesse)
        limit = 3 if slug == "vitesse" else 2
        rows: list[str] = []
        if rule_row and tok:
            since_sql = (
                f" AND a.created_at>='{campaign_since}'::timestamptz" if campaign_since else ""
            )
            sql_alerts = (
                "SELECT a.id::text, a.created_at::text, coalesce(a.evidence_snapshot::text,'null'), "
                "coalesce(a.title,'') "
                f"FROM alerts a WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{rule_row}'::uuid "
                f"{since_sql} "
                f"ORDER BY a.created_at DESC LIMIT {limit};"
            )
            rows = [r for r in psql(sql_alerts).splitlines() if r.strip()]
            if slug == "vitesse" and campaign_since:
                distinct_speed = distinct_speed_ids_since(rule_row, campaign_since)
            if not rows and event_types:
                types_sql = ",".join(f"'{t}'" for t in event_types)
                sql_events = (
                    "SELECT e.id::text, e.occurred_at::text, coalesce(e.evidence_snapshot::text,'null'), "
                    "coalesce(e.event_type,'') "
                    f"FROM events e WHERE e.org_id='{ORG}'::uuid "
                    f"AND e.event_type IN ({types_sql}) "
                    f"ORDER BY e.occurred_at DESC LIMIT {limit};"
                )
                rows = [r for r in psql(sql_events).splitlines() if r.strip()]

        for idx, line in enumerate(rows, 1):
            parts = line.split("|")
            if len(parts) < 3:
                continue
            eid, ts, snap_raw = parts[0], parts[1], parts[2]
            try:
                snap = json.loads(snap_raw) if snap_raw and snap_raw != "null" else {}
            except json.JSONDecodeError:
                snap = {}
            pkg = snap.get("package") or snap or {}
            meta = dict(pkg.get("metadata") or {})
            folder = out_wsl / slug / f"{idx:02d}_{eid[:8]}"
            folder.mkdir(parents=True, exist_ok=True)
            media: list[dict] = []
            if tok:
                for im in pkg.get("images") or []:
                    role = str(im.get("role") or im.get("kind") or "image")
                    aid = str(im.get("asset_id") or "")
                    dest = folder / f"{role}.jpg"
                    if download_asset(tok, aid, dest):
                        rel = str(dest.relative_to(out_wsl)).replace("\\", "/")
                        media.append({"role": role, "path": rel, "kind": "image", "abs": dest})
                for key, role in (
                    ("scene_asset_id", "scene"),
                    ("subject_asset_id", "subject"),
                    ("plate_asset_id", "plate"),
                ):
                    aid = str(meta.get(key) or "")
                    if not aid:
                        continue
                    dest = folder / f"{role}.jpg"
                    if dest.exists():
                        continue
                    if download_asset(tok, aid, dest):
                        rel = str(dest.relative_to(out_wsl)).replace("\\", "/")
                        media.append({"role": role, "path": rel, "kind": "image", "abs": dest})
            media = annotate_media(out_wsl, folder, media, zones, meta, slug)
            media_out = [{k: v for k, v in x.items() if k != "abs"} for x in media]
            item = {
                "id": eid,
                "ts": ts,
                "status": meta.get("evidence_status") or snap.get("status") or "",
                "capture_source": meta.get("capture_source"),
                "frigate_event_id": meta.get("frigate_event_id"),
                "media": media_out,
                "meta": {
                    k: meta.get(k)
                    for k in (
                        "evidence_status", "capture_source", "frigate_event_id",
                        "zone_id", "crop_mode", "inside_zone", "bbox", "bbox_px",
                        "speed_kmh", "camera_id", "bbox_source",
                    )
                    if meta.get(k) is not None
                },
            }
            rule_summary["items"].append(item)
            cards.append({"slug": slug, "rule": rule_name, **item})
            print(f"  {slug}#{idx} id={eid[:8]} images={len(media_out)}", flush=True)

        rule_summary["hits"] = len(rule_summary["items"])
        summary["rules"].append(rule_summary)

    diag = collect_diagnostics(step_results, {"distinct_speed_ids": distinct_speed})
    summary["diagnostics"] = diag
    (out_wsl / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8",
    )

    pass_n = sum(1 for s in step_results if s.get("status") == "PASS")
    by_slug: dict[str, list] = {}
    for c in cards:
        by_slug.setdefault(c["slug"], []).append(c)

    css = """
body{font-family:"Segoe UI",system-ui,sans-serif;margin:0;padding:28px 32px 48px;
 background:linear-gradient(165deg,#f4f6f8 0%,#e8eef4 45%,#f7f3ee 100%);color:#1a1f27}
h1{font-size:1.75rem;margin:0 0 8px;letter-spacing:-0.02em}
h2{font-size:1.2rem;margin:36px 0 14px;padding-bottom:8px;border-bottom:1px solid #c9d2dc}
h3{font-size:0.95rem;margin:0 0 10px}
.sub{color:#5a6570;margin:0 0 22px;font-size:0.95rem}
.score{font-weight:700}
.summary{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:12px;margin:18px 0 8px}
@media(max-width:900px){.summary{grid-template-columns:repeat(2,1fr)}}
.scard{background:#fff;border:1px solid #d5dde6;border-radius:10px;padding:14px 14px 12px;
 box-shadow:0 1px 0 rgba(16,24,40,.04)}
.scard .name{font-size:0.82rem;color:#5a6570;margin-bottom:6px}
.scard .video{font-size:0.8rem;color:#3d4a57;margin-top:8px}
.scard .dur{font-size:0.8rem;color:#6b7682;margin-top:4px}
.badge{display:inline-block;padding:3px 9px;border-radius:6px;font-size:12px;font-weight:650;letter-spacing:.02em}
.pass{background:#e5f6ec;color:#17663a}.fail{background:#fde8e8;color:#9b1c1c}.na{background:#eef1f4;color:#4b5563}
.card{background:#fff;border:1px solid #d5dde6;border-radius:12px;padding:16px 18px;margin:0 0 16px}
.diag-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px}
.fig{background:#0f141a;border-radius:8px;overflow:hidden;border:1px solid #cfd7e0}
.fig .cap{background:#fff;color:#3d4a57;font-size:12px;padding:6px 8px;border-top:1px solid #e5ebf1}
img{display:block;width:100%;max-height:280px;object-fit:contain;background:#0f141a}
table.kv{border-collapse:collapse;width:100%;font-size:0.9rem;margin-top:10px}
table.kv th{text-align:left;width:38%;color:#5a6570;font-weight:600;padding:5px 8px 5px 0;vertical-align:top}
table.kv td{padding:5px 0;color:#1a1f27}
.muted{color:#6b7682;font-size:0.9rem}
.detail{font-size:0.85rem;color:#3d4a57;margin-top:6px;word-break:break-word}
a{color:#1a5fb4}
.foot{margin-top:28px;color:#6b7682;font-size:0.85rem}
"""
    parts = [
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Chain-multi 5 regles — {html.escape(TS)}</title>",
        f"<style>{css}</style></head><body>",
        "<h1>Chain-multi — 5 regles demo</h1>",
        f"<p class='sub'>Run <code>{html.escape(TS)}</code> · org <code>{html.escape(ORG)}</code> · "
        f"score <span class='score'>{pass_n}/5 PASS</span> · targets 15/3/1/3/3 · "
        "<a href='summary.json'>summary.json</a> · <em>NOT DoD</em></p>",
        "<div class='summary'>",
    ]
    for slug, rule_name, _ in RULES:
        step = by_alias.get(slug) or {}
        st = str(step.get("status") or "n/a")
        cls = "pass" if st == "PASS" else ("fail" if st == "FAIL" else "na")
        video = VIDEO_LABEL.get(slug, "?")
        dur = step.get("elapsed_sec")
        short = str(step.get("detail") or "")
        if "hit=" in short:
            short = short.split("hit=", 1)[-1][:110]
        parts.append("<div class='scard'>")
        parts.append(f"<div class='name'>{html.escape(rule_name)}</div>")
        parts.append(f"<span class='badge {cls}'>{html.escape(st)}</span>")
        parts.append(f"<div class='video'>Video: <strong>{html.escape(video)}</strong></div>")
        if dur is not None:
            parts.append(f"<div class='dur'>{html.escape(str(dur))}s</div>")
        if short:
            parts.append(f"<div class='detail'>{html.escape(short)}</div>")
        parts.append("</div>")
    parts.append("</div>")

    parts.append("<h2>Diagnostics</h2>")
    parts.append(_render_diag_cards(diag))

    parts.append("<h2>Detail par regle (overlays zones)</h2>")
    for slug, rule_name, _ in RULES:
        step = by_alias.get(slug) or {}
        st = str(step.get("status") or "n/a")
        cls = "pass" if st == "PASS" else ("fail" if st == "FAIL" else "na")
        video = VIDEO_LABEL.get(slug, "?")
        parts.append("<div class='card'>")
        parts.append(
            f"<h3>{html.escape(rule_name)} "
            f"<span class='badge {cls}'>{html.escape(st)}</span></h3>"
        )
        head_rows = [
            ("Video demo", video),
            ("Duree", f"{step.get('elapsed_sec')}s" if step.get("elapsed_sec") is not None else ""),
            ("Detail", str(step.get("detail") or "")[:240]),
        ]
        parts.append(_render_kv_table([(k, v) for k, v in head_rows if v]))

        items = by_slug.get(slug) or []
        if not items:
            parts.append("<p class='muted'>Aucune preuve exportee pour cette etape.</p>")
        for it in items:
            meta = dict(it.get("meta") or {})
            item_rows = []
            if it.get("id"):
                item_rows.append(("ID", str(it.get("id"))[:36]))
            for k, label in (
                ("capture_source", "Source"),
                ("zone_id", "Zone"),
                ("crop_mode", "Crop mode"),
                ("inside_zone", "Inside zone"),
                ("frigate_event_id", "Frigate event"),
                ("outcome", "Verdict"),
                ("reason_short", "Raison"),
                ("speed_kmh", "Vitesse"),
                ("bbox_px", "BBox px"),
            ):
                v = meta.get(k)
                if v is None or v == "":
                    continue
                item_rows.append((label, json.dumps(v) if isinstance(v, (dict, list)) else str(v)))
            parts.append(_render_kv_table(item_rows))
            imgs = [m for m in (it.get("media") or []) if m.get("kind") == "image"]
            # Prefer human gallery order
            order = {"scene": 0, "scene_zones": 1, "crop": 2, "crop_zones": 3, "subject": 2, "plate": 4}
            imgs.sort(key=lambda m: order.get(str(m.get("role")), 9))
            if imgs:
                parts.append("<div class='grid'>")
                for m in imgs:
                    pth = html.escape(m["path"])
                    role = html.escape(_human_role(m.get("role") or "image"))
                    parts.append(
                        f"<div class='fig'><img src='{pth}' alt='{role}'>"
                        f"<div class='cap'>{role}</div></div>"
                    )
                parts.append("</div>")
        parts.append("</div>")

    parts.append(
        "<p class='foot'>Campagne chain-multi multi-hit — pas un claim DoD / catalogue real. "
        "Cabine: dumps VLM prioritaires (max 3). Overlays zone/bbox en lecture seule (A.1).</p>"
    )
    parts.append("</body></html>")
    (out_wsl / "index.html").write_text("\n".join(parts), encoding="utf-8")

    if out_win.resolve() != out_wsl.resolve():
        out_win.parent.mkdir(parents=True, exist_ok=True)
        if out_win.exists():
            shutil.rmtree(out_win)
        shutil.copytree(out_wsl, out_win)

    print(f"\nWSL_OUT={out_wsl}", flush=True)
    print(f"WIN_OUT={out_win}", flush=True)
    print(
        f"Open: C:\\Users\\gheno\\citevision\\validation-evidence\\chain-multi-{TS}\\index.html",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
