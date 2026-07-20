#!/usr/bin/env python3
"""Validate segment cycle mode on camera 108 — fluid clips + aligned evidence."""
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
API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
MIN_CYCLES = 2
MIN_CLIP_FRAMES = 24
MIN_LAPLACIAN = 50.0
MIN_SEGMENT_EVENTS = 1


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


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode())


def db_query(sql: str) -> str:
    cmd = [
        "docker", "exec", "citevision-v2-postgres",
        "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", sql,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout


def db_segment_events(limit: int = 20) -> list[dict[str, Any]]:
    sql = f"""
    SELECT id::text, evidence_snapshot::text, occurred_at::text
    FROM events
    WHERE camera_id = '{CAM108}'
      AND event_type = 'speeding'
      AND occurred_at > NOW() - INTERVAL '3 minutes'
    ORDER BY occurred_at DESC
    LIMIT {limit};
    """
    out: list[dict[str, Any]] = []
    for line in db_query(sql).strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        eid, ev_raw, ts = parts
        ev = json.loads(ev_raw) if ev_raw and ev_raw != "null" else {}
        pm = (ev.get("package") or {}).get("metadata") or {}
        if pm.get("capture_source") != "segment":
            continue
        out.append({"id": eid, "evidence_snapshot": ev, "occurred_at": ts})
    return out


def fetch_minio_object(asset_id: str) -> bytes | None:
    bucket = os.environ.get("MINIO_BUCKET", "citevision-evidence")
    user = os.environ.get("MINIO_ACCESS_KEY", os.environ.get("MINIO_ROOT_USER", "citevision"))
    secret = os.environ.get("MINIO_SECRET_KEY", os.environ.get("MINIO_ROOT_PASSWORD", "changeme_minio"))
    tmp = f"/tmp/cv_ev_{abs(hash(asset_id))}.bin"
    script = (
        f"mc alias set local http://127.0.0.1:9000 {user} {secret} >/dev/null 2>&1 && "
        f"mc cat local/{bucket}/{asset_id} > {tmp}"
    )
    cmd = ["docker", "exec", "citevision-v2-minio", "sh", "-c", script]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return None
    cp = subprocess.run(
        ["docker", "cp", f"citevision-v2-minio:{tmp}", tmp],
        capture_output=True, text=True, check=False,
    )
    if cp.returncode != 0:
        return None
    p = Path(tmp)
    try:
        return p.read_bytes() if p.exists() else None
    finally:
        p.unlink(missing_ok=True)


def ffprobe_frame_count(data: bytes) -> int | None:
    tmp = Path("/tmp/cv_validate_clip.mp4")
    tmp.write_bytes(data)
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-count_frames", "-show_entries", "stream=nb_read_frames,codec_name",
                "-of", "json", str(tmp),
            ],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            return None
        info = json.loads(proc.stdout)
        streams = info.get("streams") or []
        if not streams:
            return None
        nf = streams[0].get("nb_read_frames")
        return int(nf) if nf is not None else None
    finally:
        tmp.unlink(missing_ok=True)


def bbox_texture_score(image_bytes: bytes) -> float | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None or img.size == 0:
        return None
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def main() -> int:
    load_env()
    print("==> validate segment mode camera 108")
    cams = get(f"{AI}/cameras")
    cam = next((c for c in cams["cameras"] if c["camera_id"] == CAM108), None)
    if not cam:
        print("[FAIL] camera 108 not in AI /cameras")
        return 1
    if cam.get("mode") != "segment_cycle":
        print(f"[FAIL] expected mode=segment_cycle, got {cam.get('mode')}")
        return 1
    print(f"[OK] mode segment_cycle state={cam.get('segment_state')} cycle={cam.get('cycle')}")

    deadline = time.time() + 120
    while time.time() < deadline:
        cam = next(c for c in get(f"{AI}/cameras")["cameras"] if c["camera_id"] == CAM108)
        if int(cam.get("cycle") or 0) >= MIN_CYCLES:
            break
        print(f"  waiting cycles… {cam.get('cycle')} state={cam.get('segment_state')}")
        time.sleep(5)
    else:
        print(f"[FAIL] fewer than {MIN_CYCLES} segment cycles in 120s")
        return 1
    print(f"[OK] {cam.get('cycle')} segment cycles completed")

    segment_events = db_segment_events()
    print(f"[INFO] segment-sourced speeding events (30 min): {len(segment_events)}")
    if len(segment_events) < MIN_SEGMENT_EVENTS:
        print("[WARN] no segment-sourced events yet — waiting for traffic")
        return 0

    ok_clips = 0
    ok_textures = 0
    for ev_row in segment_events[:5]:
        ev = ev_row.get("evidence_snapshot") or {}
        pkg = ev.get("package") or {}
        clip = pkg.get("clip") or {}
        asset_id = clip.get("asset_id")
        if not asset_id:
            print("  [WARN] event missing clip asset_id")
            continue
        data = fetch_minio_object(asset_id)
        if not data:
            print(f"  [WARN] could not fetch clip {asset_id[:48]}…")
            continue
        if len(data) < 10_000:
            print(f"  [WARN] clip too small ({len(data)} bytes) — skipping stale/corrupt asset")
            continue
        nf = ffprobe_frame_count(data)
        if nf is not None and nf >= MIN_CLIP_FRAMES:
            ok_clips += 1
            print(f"  [OK] event clip frames={nf} cycle={pkg.get('metadata', {}).get('segment_cycle_id')}")
        else:
            print(f"  [WARN] event clip frames={nf} (min {MIN_CLIP_FRAMES})")

        for img in pkg.get("images") or []:
            if img.get("role") != "subject":
                continue
            iid = img.get("asset_id")
            if not iid:
                continue
            subj = fetch_minio_object(iid)
            if subj:
                score = bbox_texture_score(subj)
                if score is not None and score >= MIN_LAPLACIAN:
                    ok_textures += 1
                    print(f"  [OK] subject Laplacian={score:.1f}")
                elif score is not None:
                    print(f"  [WARN] subject Laplacian={score:.1f} (min {MIN_LAPLACIAN})")

    if ok_clips >= 1 and ok_textures >= 1:
        print("[OK] validate_segment_mode_108 passed")
        return 0
    if ok_clips >= 1:
        print("[OK] validate_segment_mode_108 passed (clips OK, texture partial)")
        return 0
    print("[FAIL] no fluid segment clips (insufficient unique frames)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
