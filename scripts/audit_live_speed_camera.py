#!/usr/bin/env python3
"""Audit live speed camera 108: alerts evidence quality + ingest health."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_env_file() -> None:
    for candidate in (
        ROOT / ".env",
        Path.home() / "citevision-v2" / ".env",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        break


load_env_file()
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
AI_URL = os.environ.get("AI_HEALTH_URL", "http://127.0.0.1:8001")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")
ORG = os.environ.get("AUDIT_ORG_ID", "").strip()
CAMERA_MATCH = os.environ.get("SPEED_CAMERA_MATCH", "192.168.1.108")
ALERT_LIMIT = int(os.environ.get("AUDIT_ALERT_LIMIT", "20"))
MAX_BAD_BBOX_PCT = float(os.environ.get("AUDIT_MAX_BAD_BBOX_PCT", "50"))
DEPLOY_ONLY = os.environ.get("AUDIT_DEPLOY_ONLY", "").strip() in ("1", "true", "yes")
RULE_PAUSED = os.environ.get("RULE_PAUSED", "").strip() in ("1", "true", "yes")
# Bbox/frame temporal-alignment check (Bug A / plan Phase 3.2): sample a subset
# of "subject" crops and measure edge/texture density. A crop that landed on
# empty road (misaligned bbox vs. frame) is near-uniform pavement — low
# Laplacian variance — whereas a vehicle crop has edges (glass, wheels, body
# lines, shadow) and scores meaningfully higher.
AUDIT_ALIGNMENT_SAMPLE = int(os.environ.get("AUDIT_ALIGNMENT_SAMPLE", "12"))
AUDIT_MIN_BBOX_TEXTURE_VAR = float(os.environ.get("AUDIT_MIN_BBOX_TEXTURE_VAR", "15.0"))
MAX_MISALIGNED_PCT = float(os.environ.get("AUDIT_MAX_MISALIGNED_PCT", "40"))


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def get_json(url: str, token: str | None = None) -> Any:
    return req("GET", url, token)


def bbox_valid(bb: dict | None) -> bool:
    if not bb or not isinstance(bb, dict):
        return False
    w = float(bb.get("width") or 0)
    h = float(bb.get("height") or 0)
    if w <= 0 or h <= 0:
        return False
    if w > 1.5 or h > 1.5:
        return w >= 8 and h >= 8
    return w >= 0.02 and h >= 0.02


def resolve_org(token: str) -> str:
    """Use JWT org from auth/me — DEFAULT_ORG_ID in .env is for ingest, not UI API."""
    override = os.environ.get("AUDIT_ORG_ID", "").strip()
    if override:
        return override
    me = get_json(f"{API}/api/v1/auth/me", token)
    org_id = str(me.get("org_id") or "")
    if org_id:
        return org_id
    raise SystemExit("[FAIL] no org id from auth/me")


def find_camera(token: str, org_id: str) -> dict | None:
    try:
        cams = get_json(f"{API}/api/v1/orgs/{org_id}/cameras", token)
        if isinstance(cams, list):
            for c in cams:
                name = str(c.get("name", "")).lower()
                url = str(c.get("rtsp_url", "") or c.get("stream_url", "")).lower()
                if CAMERA_MATCH.lower() in name or CAMERA_MATCH in url:
                    return c
            return cams[0] if cams else None
    except urllib.error.HTTPError:
        pass
    try:
        with urllib.request.urlopen(f"{AI_URL}/cameras", timeout=10) as resp:
            data = json.loads(resp.read().decode())
        for c in data.get("cameras") or []:
            url = str(c.get("rtsp_url", "")).lower()
            if CAMERA_MATCH in url:
                return {"id": c.get("camera_id"), "name": url, "rtsp_url": c.get("rtsp_url")}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    return None


def asset_http_ok(url: str, asset_id: str | None, org_id: str, token: str) -> bool:
    if not url and not asset_id:
        return False
    try:
        if url.startswith("http://") or url.startswith("https://"):
            full = url.replace("localhost:8081", "127.0.0.1:8081")
        elif asset_id:
            full = f"{API}/api/v1/orgs/{org_id}/evidence/assets/{asset_id}/content"
        else:
            path = url.lstrip("/")
            if path.startswith("api/v1/"):
                path = path[len("api/v1/") :]
            full = f"{API}/api/v1/{path}"
        headers = {"Authorization": f"Bearer {token}"}
        r = urllib.request.Request(full, headers=headers, method="HEAD")
        with urllib.request.urlopen(r, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        if e.code == 405:
            r2 = urllib.request.Request(full, headers={"Authorization": f"Bearer {token}"}, method="GET")
            with urllib.request.urlopen(r2, timeout=15) as resp:
                return 200 <= resp.status < 300
        return False
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def fetch_asset_bytes(url: str, asset_id: str | None, org_id: str, token: str) -> bytes | None:
    if not url and not asset_id:
        return None
    try:
        if url and (url.startswith("http://") or url.startswith("https://")):
            full = url.replace("localhost:8081", "127.0.0.1:8081")
        elif asset_id:
            full = f"{API}/api/v1/orgs/{org_id}/evidence/assets/{asset_id}/content"
        else:
            path = url.lstrip("/")
            if path.startswith("api/v1/"):
                path = path[len("api/v1/") :]
            full = f"{API}/api/v1/{path}"
        r = urllib.request.Request(full, headers={"Authorization": f"Bearer {token}"}, method="GET")
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None


def bbox_texture_score(image_bytes: bytes) -> float | None:
    """Laplacian-variance texture proxy for a subject crop. Returns None if
    image libs are unavailable or decoding fails (caller must skip, not fail,
    in that case — this is a best-effort heuristic, not a hard requirement)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    if arr.size == 0:
        return None
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None or img.size == 0:
        return None
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def parse_json_field(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def audit_alerts(token: str, org_id: str) -> dict[str, Any]:
    rows = get_json(
        f"{API}/api/v1/orgs/{org_id}/alerts?limit={ALERT_LIMIT}&include_incomplete=true",
        token,
    )
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    speed_rows = [
        a for a in rows
        if "vitesse" in str(a.get("title", "")).lower()
        or "speed" in str(a.get("title", "")).lower()
    ]
    # Prefer alerts produced by the new evidence pipeline (partial/complete metadata).
    new_fmt = []
    for a in speed_rows:
        ev = parse_json_field(a.get("evidence_snapshot"))
        pkg = ev.get("package") if isinstance(ev.get("package"), dict) else {}
        meta = pkg.get("metadata") if isinstance(pkg.get("metadata"), dict) else {}
        if meta.get("evidence_status") in ("partial", "complete"):
            new_fmt.append(a)
    if new_fmt:
        speed_rows = new_fmt[:ALERT_LIMIT]
    elif not speed_rows:
        speed_rows = rows[:ALERT_LIMIT]
    else:
        speed_rows = speed_rows[:ALERT_LIMIT]

    total = len(speed_rows)
    bad_bbox = 0
    plate_404 = 0
    plate_ok = 0
    has_scene = 0
    has_subject = 0
    missing_plate_meta = 0
    subject_refs: list[tuple[str, str | None]] = []  # (url, asset_id) for alignment sampling

    for a in speed_rows:
        ev = parse_json_field(a.get("evidence_snapshot"))
        if not ev:
            ev = parse_json_field(a.get("evidence"))
        pkg = ev.get("package") if isinstance(ev.get("package"), dict) else {}
        meta = pkg.get("metadata") if isinstance(pkg.get("metadata"), dict) else {}
        if not meta and isinstance(ev, dict):
            meta = ev
        bb = meta.get("bbox") or ev.get("bbox")
        if not bbox_valid(bb):
            bad_bbox += 1
        status = meta.get("evidence_status")
        missing = meta.get("missing_roles") if isinstance(meta.get("missing_roles"), list) else []
        if status == "partial" and "plate" in missing:
            missing_plate_meta += 1
        images = pkg.get("images") or []
        for img in images:
            if not isinstance(img, dict):
                continue
            role = img.get("role")
            url = img.get("url") or ""
            if role == "scene" and (url or img.get("asset_id")):
                has_scene += 1
            if role == "subject" and (url or img.get("asset_id")):
                has_subject += 1
                subject_refs.append((url, img.get("asset_id")))
            if role == "plate" and "plate" not in missing:
                aid = img.get("asset_id")
                if url or aid:
                    if asset_http_ok(url, aid, org_id, token):
                        plate_ok += 1
                    else:
                        plate_404 += 1
        if isinstance(meta.get("missing_roles"), list) and "plate" in meta["missing_roles"] and status != "partial":
            missing_plate_meta += 1

    alignment_sampled = 0
    alignment_misaligned = 0
    alignment_scores: list[float] = []
    alignment_skipped_libs = False
    for url, asset_id in subject_refs[:AUDIT_ALIGNMENT_SAMPLE]:
        raw = fetch_asset_bytes(url, asset_id, org_id, token)
        if raw is None:
            continue
        score = bbox_texture_score(raw)
        if score is None:
            alignment_skipped_libs = True
            continue
        alignment_sampled += 1
        alignment_scores.append(score)
        if score < AUDIT_MIN_BBOX_TEXTURE_VAR:
            alignment_misaligned += 1

    return {
        "total": total,
        "bad_bbox": bad_bbox,
        "plate_404": plate_404,
        "plate_ok": plate_ok,
        "has_scene": has_scene,
        "has_subject": has_subject,
        "missing_plate_meta": missing_plate_meta,
        "alignment_sampled": alignment_sampled,
        "alignment_misaligned": alignment_misaligned,
        "alignment_scores": alignment_scores,
        "alignment_skipped_libs": alignment_skipped_libs,
    }


def audit_ingest(camera_id: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ai_ok": False}
    try:
        with urllib.request.urlopen(f"{AI_URL}/health", timeout=5) as resp:
            health = json.loads(resp.read().decode())
        out["ai_ok"] = health.get("status") == "ok"
        out["gpu"] = health.get("gpu")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return out
    try:
        with urllib.request.urlopen(f"{AI_URL}/cameras", timeout=10) as resp:
            data = json.loads(resp.read().decode())
        cams = data.get("cameras") or []
        out["camera_count"] = len(cams)
        for c in cams:
            cid = str(c.get("camera_id", ""))
            if camera_id and cid != camera_id:
                continue
            if not camera_id and CAMERA_MATCH not in str(c.get("rtsp_url", "")):
                continue
            out["frames_processed"] = c.get("frames_processed")
            out["fps"] = c.get("fps")
            out["running"] = c.get("running")
            break
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    return out


def main() -> int:
    print("==> audit live speed camera")
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login.get("access_token")
    if not token:
        print("[FAIL] login")
        return 1
    org_id = resolve_org(token)
    cam = find_camera(token, org_id)
    cam_id = str(cam.get("id") or cam.get("camera_id") or "") if cam else ""
    if cam:
        print(f"[OK] camera: {cam.get('name')} ({cam_id})")
    else:
        print(f"[WARN] no camera matching {CAMERA_MATCH}")

    ingest = audit_ingest(cam_id or None)
    print(f"[INFO] AI health: {ingest}")
    if not ingest.get("ai_ok"):
        print("[FAIL] AI not healthy")
        return 1

    stats = audit_alerts(token, org_id)
    try:
        events = get_json(f"{API}/api/v1/orgs/{org_id}/events?limit=200&event_type=speeding", token)
        if isinstance(events, dict):
            events = events.get("items", [])
        speed_events = len(events) if isinstance(events, list) else 0
    except urllib.error.URLError:
        speed_events = -1

    complete = stats["total"] - stats["bad_bbox"]
    partial = stats["missing_plate_meta"]
    align_sampled = stats["alignment_sampled"]
    align_bad = stats["alignment_misaligned"]
    align_pct = 100.0 * align_bad / max(align_sampled, 1) if align_sampled else 0.0
    print("=== RAPPORT CHIFFRÉ (avant réactivation règle) ===")
    print(f"  alertes vitesse auditées     : {stats['total']}")
    print(f"  bbox valides                 : {complete}/{stats['total']}")
    print(f"  preuves partielles (plaque)  : {partial}")
    print(f"  assets plaque OK / 404       : {stats['plate_ok']} / {stats['plate_404']}")
    print(f"  événements speeding (API)    : {speed_events}")
    print(f"  ingest 108 frames/fps        : {ingest.get('frames_processed')} / {ingest.get('fps')}")
    print(f"  caméra 108 running           : {ingest.get('running')}")
    if stats["alignment_skipped_libs"]:
        print("  alignement bbox/frame        : SKIPPED (cv2/numpy indisponibles dans cet interpréteur — utilisez AI_VENV_PYTHON)")
    else:
        print(f"  alignement bbox/frame        : {align_sampled - align_bad}/{align_sampled} crops texturés (probable véhicule), {align_bad} suspects (route vide)")
        if stats["alignment_scores"]:
            print(f"  texture Laplacian (min/moy/max): {min(stats['alignment_scores']):.1f} / {sum(stats['alignment_scores'])/len(stats['alignment_scores']):.1f} / {max(stats['alignment_scores']):.1f}")
    print(f"[REPORT] detail: {stats}")

    if stats["total"] == 0:
        print("[WARN] no speed alerts to audit (rule may be paused — OK for deploy)")
        return 0

    soft = DEPLOY_ONLY or RULE_PAUSED
    bad_pct = 100.0 * stats["bad_bbox"] / max(stats["total"], 1)
    if bad_pct > MAX_BAD_BBOX_PCT:
        if soft:
            print(f"[WARN] {bad_pct:.0f}% alerts without valid bbox (legacy/pre-pause — re-test after rule ON)")
        else:
            print(f"[FAIL] {bad_pct:.0f}% alerts without valid bbox (max {MAX_BAD_BBOX_PCT}%)")
            return 1
    if stats["plate_404"] > 0:
        if soft:
            print(f"[WARN] {stats['plate_404']} complete alerts with plate asset HTTP error (check retention)")
        else:
            print(f"[FAIL] {stats['plate_404']} plate assets return HTTP error")
            return 1

    if align_sampled and align_pct > MAX_MISALIGNED_PCT:
        if soft:
            print(f"[WARN] {align_pct:.0f}% subject crops look misaligned (low texture — legacy/pre-pause, re-test after rule ON)")
        else:
            print(f"[FAIL] {align_pct:.0f}% subject crops look misaligned with the vehicle (max {MAX_MISALIGNED_PCT}%)")
            return 1

    if soft:
        print("[OK] deploy audit passed (rule paused — réactivez puis surveillez 5 min)")
    else:
        print("[OK] live speed audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
