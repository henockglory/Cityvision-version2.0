#!/usr/bin/env python3
"""Audit qualite des preuves stockees (DB + MinIO) — sans camera, lecture seule.

Classifie les evenements speeding selon le handoff §8.2 :
  H1 segment          : capture_source == 'segment' (mode abandonne, preuves suspectes)
  H2 live_async       : pas de capture_source ni bbox_ts (ancien pipeline async desaligne)
  H3 clip_micro       : clip < 1 Ko (bug segment / ffmpeg)
  H4 complete_empty   : evidence_status=complete mais subject sans texture (Laplacian bas)
  H5 bbox_misalign     : bbox_quality_ok=false ou frigate_track sans frigate_event_id
  OK                  : subject texture suffisante et metadonnees coherentes

Sortie : rapport console + CSV scripts/evidence_audit_report.csv

Usage (WSL, runtime ~/citevision-v2) :
  python3 scripts/audit_evidence_quality.py --limit 100
  python3 scripts/audit_evidence_quality.py --camera-id <uuid> --csv /tmp/report.csv

Conforme [P.135] : aucune ecriture DB, lecture seule.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
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
        "psql", "-U", "citevision", "-d", "citevision",
        "-t", "-A", "-F", "\x1f", "-c", sql,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        print(f"[ERR] psql: {res.stderr.strip()[:300]}", file=sys.stderr)
    return res.stdout


_minio_client = None


def minio_client():
    global _minio_client
    if _minio_client is not None:
        return _minio_client
    try:
        from minio import Minio
    except ImportError:
        return None
    endpoint = os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000")
    secure = os.environ.get("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
    if endpoint.startswith("https://"):
        endpoint, secure = endpoint[len("https://"):], True
    elif endpoint.startswith("http://"):
        endpoint = endpoint[len("http://"):]
    endpoint = endpoint.rstrip("/")
    user = os.environ.get("MINIO_ACCESS_KEY", os.environ.get("MINIO_ROOT_USER", "citevision"))
    secret = os.environ.get("MINIO_SECRET_KEY", os.environ.get("MINIO_ROOT_PASSWORD", "changeme_minio"))
    _minio_client = Minio(endpoint, access_key=user, secret_key=secret, secure=secure)
    return _minio_client


def minio_stat_and_get(object_key: str, want_bytes: bool = True) -> tuple[int | None, bytes | None]:
    client = minio_client()
    if client is None or not object_key:
        return None, None
    bucket = os.environ.get("MINIO_BUCKET", "citevision-evidence")
    try:
        stat = client.stat_object(bucket, object_key)
        size = int(stat.size or 0)
        data = None
        if want_bytes:
            resp = client.get_object(bucket, object_key)
            data = resp.read()
            resp.close()
            resp.release_conn()
        return size, data
    except Exception:
        return None, None


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


def object_key_for(imgs: list[dict], role: str) -> str:
    for i in imgs:
        if i.get("role") == role:
            return str(i.get("object_key") or i.get("asset_id") or "")
    return ""


def classify(row: dict[str, Any], min_texture: float) -> tuple[str, dict[str, Any]]:
    """Return (class, details) for one event row. Classes: H1/H2/H3/H4/OK/NO_ASSETS."""
    snap = row["snapshot"]
    pkg = snap.get("package") or {}
    meta = pkg.get("metadata") or {}
    src = meta.get("capture_source") or ""
    status = meta.get("evidence_status") or "unknown"
    bbox_ts = meta.get("bbox_ts")
    imgs = pkg.get("images") or []
    clip = pkg.get("clip") or {}

    details: dict[str, Any] = {
        "capture_source": src or "unknown",
        "evidence_status": status,
        "bbox_ts": bbox_ts,
        "bbox_quality_ok": meta.get("bbox_quality_ok"),
        "frigate_event_id": meta.get("frigate_event_id"),
        "clip_size": None,
        "subject_texture": None,
    }

    if src == "segment":
        return "H1", details

    if meta.get("bbox_quality_ok") is False:
        return "H5", details
    if src == "frigate_track" and not meta.get("frigate_event_id"):
        return "H5", details

    clip_key = str(clip.get("object_key") or clip.get("asset_id") or "")
    if clip_key:
        size, _ = minio_stat_and_get(clip_key, want_bytes=False)
        details["clip_size"] = size
        if size is not None and size < 1024:
            return "H3", details

    subj_key = object_key_for(imgs, "subject")
    if not imgs and not clip_key:
        return "NO_ASSETS", details
    if subj_key:
        _, jpeg = minio_stat_and_get(subj_key)
        if jpeg:
            tex = laplacian_var(jpeg)
            details["subject_texture"] = round(tex, 1) if tex is not None else None
            if tex is not None and tex < min_texture:
                if status == "complete":
                    return "H4", details
                return "H4_flagged" if meta.get("bbox_quality_ok") is False else "H4", details

    if not src and bbox_ts is None:
        return "H2", details
    return "OK", details


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description="Audit qualite preuves stockees (lecture seule)")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--camera-id", default="")
    ap.add_argument("--event-type", default="speeding")
    ap.add_argument("--min-texture", type=float, default=50.0,
                    help="Seuil Laplacian subject (handoff §8.3 : <50 = rate)")
    ap.add_argument("--csv", default=str(ROOT / "scripts" / "evidence_audit_report.csv"))
    args = ap.parse_args()

    cam_filter = f"AND camera_id = '{args.camera_id}'" if args.camera_id else ""
    sql = f"""
    SELECT e.id::text, e.camera_id::text, e.occurred_at::text, e.evidence_snapshot::text
    FROM events e
    WHERE e.event_type = '{args.event_type}'
      AND e.evidence_snapshot IS NOT NULL
      AND e.evidence_snapshot::text NOT IN ('null', '{{}}')
      {cam_filter}
    ORDER BY e.occurred_at DESC
    LIMIT {args.limit};
    """
    rows: list[dict[str, Any]] = []
    for line in db_query(sql).strip().splitlines():
        parts = line.split("\x1f")
        if len(parts) < 4:
            continue
        try:
            snap = json.loads(parts[3]) if parts[3] and parts[3] != "null" else {}
        except json.JSONDecodeError:
            snap = {}
        rows.append({"id": parts[0], "camera_id": parts[1], "occurred_at": parts[2], "snapshot": snap})

    if not rows:
        print(f"[WARN] aucun evenement {args.event_type} avec evidence_snapshot")
        return 0

    counts: dict[str, int] = {}
    csv_rows: list[dict[str, Any]] = []
    print(f"==> audit {len(rows)} evenements {args.event_type} (min_texture={args.min_texture})")
    for row in rows:
        cls, details = classify(row, args.min_texture)
        counts[cls] = counts.get(cls, 0) + 1
        rec = {
            "event_id": row["id"],
            "camera_id": row["camera_id"],
            "occurred_at": row["occurred_at"],
            "class": cls,
            **details,
        }
        csv_rows.append(rec)
        print(
            f"  {row['occurred_at'][:19]} {row['id'][:8]} [{cls:>10}] "
            f"src={details['capture_source']} status={details['evidence_status']} "
            f"texture={details['subject_texture']} clip={details['clip_size']}"
        )

    csv_path = Path(args.csv)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    total = len(rows)
    ok = counts.get("OK", 0)
    print("=== SUMMARY ===")
    print(json.dumps({"total": total, **counts, "ok_pct": round(100.0 * ok / total, 1)}, indent=2))
    print(f"CSV: {csv_path}")

    legacy = counts.get("H1", 0) + counts.get("H2", 0)
    if legacy:
        print(f"[INFO] {legacy} preuves legacy (H1 segment / H2 async) — non regenerables, voir handoff §8.4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
