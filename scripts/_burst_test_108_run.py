#!/usr/bin/env python3
"""Test rafale cam 108 — orchestration (lecture seule, pas de modif code)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
AI = "http://127.0.0.1:8001"
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")
TARGET = int(os.environ.get("BURST_TARGET", "10"))
POLL_SEC = int(os.environ.get("BURST_POLL_SEC", "20"))
TIMEOUT_SEC = int(os.environ.get("BURST_TIMEOUT_SEC", "1200"))
MIN_TEXTURE = float(os.environ.get("AUDIT_MIN_TEXTURE", "50"))
REPORT = ROOT / "scripts" / "_burst_test_108_report.txt"


def load_env() -> None:
    for p in (ROOT / ".env", Path.home() / "citevision-v2" / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        break


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> Any:
    h = {"Content-Type": "application/json"}
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
        capture_output=True, text=True,
    )
    return (proc.stdout or proc.stderr).strip()


def psql_count(sql: str) -> int:
    for line in psql(sql).splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def get_cam108() -> dict | None:
    try:
        data = req("GET", f"{AI}/cameras")
        for c in data.get("cameras") or []:
            if c.get("camera_id") == CAM108:
                return c
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    return None


def laplacian(jpeg: bytes) -> float | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    arr = np.frombuffer(jpeg, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None or img.size == 0:
        return None
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def fetch_asset(token: str, org_id: str, url: str, asset_id: str) -> tuple[int, bytes | None]:
    if url.startswith("http"):
        full = url.replace("localhost:8081", "127.0.0.1:8081")
    elif asset_id:
        full = f"{API}/api/v1/orgs/{org_id}/evidence/asset?key={urllib.parse.quote(asset_id, safe='')}"
    else:
        return 0, None
    try:
        r = urllib.request.Request(full, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(r, timeout=20) as resp:
            data = resp.read()
            return len(data), data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return 0, None


def audit_event(token: str, org_id: str, row: dict) -> dict[str, Any]:
    snap = row.get("snapshot") or {}
    pkg = snap.get("package") or {}
    meta = pkg.get("metadata") or {}
    imgs = pkg.get("images") or []
    clip = pkg.get("clip") or {}
    src = meta.get("capture_source") or "unknown"
    status = meta.get("evidence_status") or "unknown"
    quality_ok = meta.get("bbox_quality_ok")
    bbox_ts = meta.get("bbox_ts")
    subject = next((i for i in imgs if i.get("role") == "subject"), {})
    subj_url = subject.get("url") or ""
    subj_id = subject.get("asset_id") or ""
    subj_size, subj_bytes = fetch_asset(token, org_id, subj_url, subj_id)
    tex = laplacian(subj_bytes) if subj_bytes else None
    if tex is None:
        stored = meta.get("subject_texture")
        if isinstance(stored, (int, float)):
            tex = float(stored)
    clip_id = clip.get("asset_id") or ""
    clip_url = clip.get("url") or ""
    clip_size, clip_bytes = fetch_asset(token, org_id, clip_url, clip_id)
    has_ftyp = bool(clip_bytes and b"ftyp" in clip_bytes[:64])
    ok = (
        src == "live"
        and bbox_ts is not None
        and (quality_ok is True or quality_ok is None)
        and tex is not None and tex >= MIN_TEXTURE
        and clip_size >= 1024 and has_ftyp
        and status in ("complete", "partial")
    )
    if src == "segment":
        ok = False
    if quality_ok is False:
        ok = False
    if tex is not None and tex < MIN_TEXTURE:
        ok = False
    if status == "complete" and tex is not None and tex < MIN_TEXTURE:
        ok = False
    return {
        "event_id": row["id"],
        "occurred_at": row["occurred_at"],
        "src": src,
        "status": status,
        "quality_ok": quality_ok,
        "bbox_ts": bbox_ts,
        "subject_texture": round(tex, 1) if tex is not None else None,
        "subject_size": subj_size,
        "clip_size": clip_size,
        "clip_ftyp": has_ftyp,
        "verdict": "OK" if ok else "KO",
    }


def fetch_fresh_events(marker: str) -> list[dict]:
    raw = psql(
        f"SELECT id::text, occurred_at::text, evidence_snapshot::text FROM events "
        f"WHERE camera_id='{CAM108}' AND event_type='speeding' "
        f"AND occurred_at > '{marker}' ORDER BY occurred_at DESC LIMIT 20;"
    )
    rows: list[dict] = []
    for line in raw.splitlines():
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        try:
            snap = json.loads(parts[2]) if parts[2] and parts[2] != "null" else {}
        except json.JSONDecodeError:
            snap = {}
        rows.append({"id": parts[0], "occurred_at": parts[1], "snapshot": snap})
    return rows


def main() -> int:
    load_env()
    lines: list[str] = []
    def log(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    log("=== BURST TEST CAM 108 ===")
    health = req("GET", f"{AI}/health")
    log(f"AI health: {health.get('status')} cuda={health.get('yolo_cuda')}")

    cam = get_cam108()
    if not cam:
        log("[FAIL] cam 108 not found on AI")
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        return 1
    fp0 = int(cam.get("frames_processed") or cam.get("frames_read") or 0)
    log(f"cam108 running={cam.get('running')} last_error={cam.get('last_error')} fp={fp0}")
    if cam.get("last_error"):
        log("[WARN] last_error set — run restore_live_mode_108.py manually if needed")

    time.sleep(30)
    cam2 = get_cam108() or cam
    fp1 = int(cam2.get("frames_processed") or cam2.get("frames_read") or 0)
    log(f"RTSP delta 30s: {fp1 - fp0} frames")

    marker = psql("SELECT now()::text;").strip()
    log(f"T0 marker={marker}")
    baseline = psql_count(
        f"SELECT count(*) FROM events WHERE camera_id='{CAM108}' AND event_type='speeding' "
        f"AND occurred_at > '{marker}';"
    )
    log(f"baseline speeding since T0: {baseline}")

    deadline = time.time() + TIMEOUT_SEC
    ingest_log: list[str] = []
    last_minute = time.time()
    while time.time() < deadline:
        n = psql_count(
            f"SELECT count(*) FROM events WHERE camera_id='{CAM108}' AND event_type='speeding' "
            f"AND occurred_at > '{marker}';"
        )
        new = n - baseline
        if time.time() - last_minute >= 60:
            c = get_cam108() or {}
            ingest_log.append(
                f"  ingest: fp={c.get('frames_processed')} dropped={c.get('frames_dropped')} "
                f"queue={c.get('queue_depth')} latency_ms={c.get('infer_latency_ms')}"
            )
            log(ingest_log[-1])
            last_minute = time.time()
        log(f"new_speeding={new}/{TARGET}")
        if new >= TARGET:
            break
        time.sleep(POLL_SEC)
    else:
        log(f"[TIMEOUT] only {new}/{TARGET} events after {TIMEOUT_SEC}s")

    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login.get("access_token")
    if not token:
        log("[FAIL] login")
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        return 1
    me = req("GET", f"{API}/api/v1/auth/me", token=token)
    org_id = str(me.get("org_id") or ORG)

    fresh = fetch_fresh_events(marker)
    log(f"\n=== AUDIT {len(fresh)} FRESH EVENTS ===")
    results = [audit_event(token, org_id, r) for r in fresh[:TARGET]]
    ok_n = sum(1 for r in results if r["verdict"] == "OK")
    tex_ok = sum(1 for r in results if r["subject_texture"] is not None and r["subject_texture"] >= MIN_TEXTURE)
    segment_n = sum(1 for r in results if r["src"] == "segment")

    log(f"{'event_id':<38} {'at':<22} {'src':<8} {'status':<10} {'q_ok':<6} {'tex':<8} {'clip':<8} verdict")
    for r in results:
        log(
            f"{r['event_id'][:36]:<38} {r['occurred_at'][:19]:<22} {r['src']:<8} "
            f"{r['status']:<10} {str(r['quality_ok']):<6} {str(r['subject_texture']):<8} "
            f"{r['clip_size']:<8} {r['verdict']}"
        )

    pct = 100.0 * tex_ok / max(len(results), 1)
    ingest_stable = fp1 > fp0
    pass_global = (
        new >= TARGET
        and ok_n >= 8
        and segment_n == 0
        and pct >= 80.0
        and ingest_stable
    )
    log("\n=== SUMMARY ===")
    log(f"events_collected={new} audited={len(results)} ok={ok_n} texture_ok={tex_ok} ({pct:.0f}%)")
    log(f"segment_legacy={segment_n} ingest_stable={ingest_stable}")
    log(f"VERDICT={'PASS' if pass_global else 'FAIL'}")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    log(f"Report: {REPORT}")
    return 0 if pass_global else 1


if __name__ == "__main__":
    raise SystemExit(main())
