#!/usr/bin/env python3
"""Diagnose one recent demo event with no alert — why evidence/alert was suppressed."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
FRIGATE = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip()


def post_internal(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-Internal-Key": INTERNAL},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def frigate_events(cam_id: str, limit: int = 5) -> list:
    import urllib.parse
    fid = f"cv_{cam_id}"
    qs = urllib.parse.urlencode({"cameras": fid, "limit": limit})
    with urllib.request.urlopen(f"{FRIGATE}/api/events?{qs}", timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return data if isinstance(data, list) else []


def package_ok(pkg: dict | None) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if not pkg:
        return False, ["no package"]
    clip = pkg.get("clip") or {}
    if not clip.get("url") and not clip.get("asset_id"):
        missing.append("clip")
    roles: set[str] = set()
    for im in pkg.get("images") or []:
        if isinstance(im, dict) and im.get("role") and (im.get("url") or im.get("asset_id")):
            roles.add(str(im["role"]))
    for need in ("scene", "subject"):
        if need not in roles:
            missing.append(f"image:{need}")
    meta = pkg.get("metadata") or {}
    if meta.get("bbox_quality_ok") is False:
        missing.append("bbox_quality_ok=false")
    if meta.get("capture_source") != "frigate_track":
        missing.append(f"capture_source={meta.get('capture_source')}")
    return len(missing) == 0, missing


def main() -> int:
    print("=== Diagnostic preuve — 1 event sans alerte ===", flush=True)
    row = psql(
        f"SELECT e.id::text, e.event_type, e.camera_id::text, e.ingested_at::text, "
        f"e.payload::text, COALESCE(r.name, '') "
        f"FROM events e "
        f"JOIN cameras c ON c.id=e.camera_id "
        f"LEFT JOIN alerts a ON a.event_id=e.id "
        f"LEFT JOIN rules r ON r.id=(e.payload->>'rule_id')::uuid "
        f"WHERE c.org_id='{ORG}'::uuid AND c.metadata->>'demo'='true' "
        f"AND e.event_type IN ('speeding','red_light_violation','phone_use_violation','phone_driving','driver_phone') "
        f"AND e.ingested_at > now() - interval '3 hours' "
        f"AND a.id IS NULL "
        f"ORDER BY e.ingested_at DESC LIMIT 1;"
    )
    if not row or "|" not in row:
        print("  no recent event without alert in last 3h", flush=True)
        return 0

    parts = row.split("|", 5)
    evt_id, etype, cam_id, ingested, payload_raw, rule_name = parts
    print(f"  event_id={evt_id[:8]} type={etype} cam={cam_id[:8]} rule={rule_name}", flush=True)
    print(f"  ingested_at={ingested}", flush=True)

    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except json.JSONDecodeError:
        payload = {}

    fe = frigate_events(cam_id, 8)
    print(f"  frigate_events={len(fe)} for cv_{cam_id[:8]}", flush=True)
    if fe:
        anchor = payload.get("bbox_ts") or payload.get("timestamp")
        for ev in fe[:3]:
            st = ev.get("start_time")
            delta = abs(float(st) - float(anchor)) if anchor and st else "?"
            print(f"    frigate id={str(ev.get('id',''))[:20]} start={st} delta={delta}s label={ev.get('label')}", flush=True)

    ev_body = {**payload, "event_id": evt_id, "event_type": etype, "camera_id": cam_id}
    policy = {
        "enabled": True,
        "clip_seconds": 6,
        "images": [
            {"role": "scene", "crop": "full"},
            {"role": "subject", "crop": "bbox"},
        ],
    }
    try:
        resp = post_internal(f"/api/v1/internal/orgs/{ORG}/evidence/request", {
            "camera_id": cam_id,
            "event": ev_body,
            "evidence": policy,
        })
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()[:400]
        print(f"  evidence/request HTTP {exc.code}: {body}", flush=True)
        return 1
    except urllib.error.URLError as exc:
        print(f"  evidence/request failed: {exc}", flush=True)
        print("  => backend down? bash scripts/_restart_backend.sh", flush=True)
        return 1

    pkg = resp.get("package") or (resp.get("evidence") or {}).get("package")
    ok, missing = package_ok(pkg if isinstance(pkg, dict) else None)
    meta = (pkg or {}).get("metadata") or {}
    print(f"  retro_capture ok={ok} missing={missing}", flush=True)
    if meta:
        print(f"  meta: capture_source={meta.get('capture_source')} align_delta_ms={meta.get('align_delta_ms')} "
              f"bbox_source={meta.get('bbox_source')} status={meta.get('evidence_status')}", flush=True)
    if resp.get("error"):
        print(f"  error={resp.get('error')}", flush=True)

    print("\n  rules-engine log (last suppressions):", flush=True)
    subprocess.run(
        ["grep", "-E", "alert suppressed|ensureEvidencePackage", f"{os.path.expanduser('~')}/citevision-v2/logs/rules-engine.log"],
        capture_output=False,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
