#!/usr/bin/env python3
"""Audit stored speeding evidence (DB + MinIO) — no RTSP / no cam 108 required.

Usage (WSL):
  python3 ~/citevision-v2/scripts/audit_stored_speed_evidence.py
  python3 scripts/audit_stored_speed_evidence.py --limit 50 --camera-id <uuid>

Exit 0 if >= MIN_OK_PCT of sampled subjects pass texture check (post-fix cohort).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


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


def db_query(sql: str) -> str:
    cmd = [
        "docker", "exec", "citevision-v2-postgres",
        "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "\t", "-c", sql,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout


def minio_get(object_key: str) -> bytes | None:
    try:
        from minio import Minio
    except ImportError:
        return None
    endpoint = os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000")
    secure = os.environ.get("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
    user = os.environ.get("MINIO_ACCESS_KEY", os.environ.get("MINIO_ROOT_USER", "citevision"))
    secret = os.environ.get("MINIO_SECRET_KEY", os.environ.get("MINIO_ROOT_PASSWORD", "changeme_minio"))
    bucket = os.environ.get("MINIO_BUCKET", "citevision-evidence")
    client = Minio(endpoint, access_key=user, secret_key=secret, secure=secure)
    try:
        resp = client.get_object(bucket, object_key)
        data = resp.read()
        resp.close()
        resp.release_conn()
        return data
    except Exception:
        return None


def laplacian_var(jpeg: bytes) -> float | None:
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


def subject_object_key(org_id: str, camera_id: str, event_id: str) -> str:
    return f"orgs/{org_id}/cameras/{camera_id}/events/{event_id}/subject.jpg"


def parse_rows(raw: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in raw.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        eid, cam, occurred, snap_raw = parts[0], parts[1], parts[2], parts[3]
        snap = json.loads(snap_raw) if snap_raw and snap_raw != "null" else {}
        out.append({"id": eid, "camera_id": cam, "occurred_at": occurred, "snapshot": snap})
    return out


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description="Audit stored speeding evidence quality")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("AUDIT_STORED_LIMIT", "40")))
    ap.add_argument("--camera-id", default=os.environ.get("AUDIT_CAMERA_ID", ""))
    ap.add_argument("--min-texture", type=float, default=float(os.environ.get("AUDIT_MIN_TEXTURE", "15")))
    ap.add_argument("--min-ok-pct", type=float, default=float(os.environ.get("AUDIT_MIN_OK_PCT", "70")))
    args = ap.parse_args()

    cam_filter = f"AND camera_id = '{args.camera_id}'" if args.camera_id else ""
    sql = f"""
    SELECT e.id::text, e.camera_id::text, e.occurred_at::text, e.evidence_snapshot::text
    FROM events e
    WHERE e.event_type = 'speeding'
      AND e.evidence_snapshot IS NOT NULL
      AND e.evidence_snapshot::text NOT IN ('null', '{{}}')
      {cam_filter}
    ORDER BY e.occurred_at DESC
    LIMIT {args.limit};
    """
    rows = parse_rows(db_query(sql))
    if not rows:
        print("[WARN] no speeding events with evidence_snapshot")
        return 0

    org_id = os.environ.get("AUDIT_ORG_ID", "")
    stats = {"total": 0, "segment": 0, "live": 0, "no_subject": 0, "ok": 0, "empty": 0, "partial": 0}

    print(f"==> audit {len(rows)} stored speeding events (min_texture={args.min_texture})")
    for row in rows:
        snap = row["snapshot"]
        pkg = snap.get("package") or {}
        meta = pkg.get("metadata") or {}
        src = meta.get("capture_source") or "live"
        status = meta.get("evidence_status") or "unknown"
        stats["total"] += 1
        if src == "segment":
            stats["segment"] += 1
        else:
            stats["live"] += 1
        if status == "partial":
            stats["partial"] += 1

        org = org_id or meta.get("org_id") or snap.get("org_id") or ""
        if not org:
            pkg_org = (pkg.get("clip") or {}).get("url") or ""
            if "/orgs/" in pkg_org:
                org = pkg_org.split("/orgs/")[1].split("/")[0]

        imgs = pkg.get("images") or []
        subject = next((i for i in imgs if i.get("role") == "subject"), None)
        jpeg: bytes | None = None
        if subject and subject.get("object_key") and org:
            jpeg = minio_get(subject["object_key"])
        elif subject and subject.get("asset_id") and org:
            jpeg = minio_get(subject_object_key(org, row["camera_id"], row["id"]))
        if jpeg is None and org:
            jpeg = minio_get(subject_object_key(org, row["camera_id"], row["id"]))

        if not jpeg:
            stats["no_subject"] += 1
            print(f"  {row['occurred_at'][:19]} {row['id'][:8]} src={src} status={status} NO_SUBJECT")
            continue

        score = laplacian_var(jpeg)
        ok = score is not None and score >= args.min_texture
        if ok:
            stats["ok"] += 1
        else:
            stats["empty"] += 1
        print(
            f"  {row['occurred_at'][:19]} {row['id'][:8]} src={src} status={status} "
            f"texture={score if score is not None else 'NA'} {'OK' if ok else 'EMPTY'}"
        )

    scored = stats["ok"] + stats["empty"]
    ok_pct = 100.0 * stats["ok"] / max(scored, 1)
    print("=== SUMMARY ===")
    print(json.dumps({**stats, "ok_pct": round(ok_pct, 1)}, indent=2))

    live_scored = stats["total"] - stats["segment"]
    if live_scored == 0:
        print("[WARN] no live-mode events in sample")
        return 0
    if ok_pct < args.min_ok_pct:
        print(f"[FAIL] only {ok_pct:.0f}% subjects pass texture (min {args.min_ok_pct}%)")
        return 1
    print(f"[OK] {ok_pct:.0f}% subjects pass texture check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
