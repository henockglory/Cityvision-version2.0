#!/usr/bin/env python3
"""Audit fresh alerts since 1 km/h marker."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
CAM = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
MARKER = "2026-07-08 07:04:41+00"
API = "http://127.0.0.1:8081"


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


load_env()


def login() -> str:
    body = json.dumps({"email": os.environ.get("DEMO_USER", "admin@demo.local"), "password": os.environ.get("DEMO_PASS", "demo1234")}).encode()
    req = urllib.request.Request(f"{API}/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]


def get(url: str, token: str) -> list:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data if isinstance(data, list) else data.get("items", [])


def psql(sql: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
        capture_output=True, text=True,
    )
    return proc.stdout or proc.stderr


def main() -> None:
    token = login()
    alerts = get(f"{API}/api/v1/orgs/{ORG}/alerts?limit=50&include_incomplete=true", token)
    fresh = []
    for a in alerts:
        meta = a.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        if meta.get("camera_id") != CAM:
            continue
        if meta.get("event_type") != "speeding":
            continue
        created = a.get("created_at", "")
        if created >= MARKER.replace("+00", "Z") or created >= MARKER:
            fresh.append(a)

    print(f"=== ALERTES FRAÎCHES (depuis limite 1 km/h) : {len(fresh)} ===")
    has_scene = has_subject = has_clip = has_bbox = has_bbox_ts = 0
    speeds = []
    for a in fresh[:15]:
        meta = a.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        ev = a.get("evidence_snapshot") or meta.get("evidence_snapshot") or {}
        if isinstance(ev, str):
            ev = json.loads(ev)
        pkg = (ev.get("package") or meta.get("package") or {}) if isinstance(ev, dict) else {}
        if isinstance(pkg, str):
            pkg = json.loads(pkg)
        pm = pkg.get("metadata") or {}
        bb = pm.get("bbox") or meta.get("bbox")
        bbox_ts = pm.get("bbox_ts") or meta.get("bbox_ts")
        speed = meta.get("speed_kmh") or pm.get("speed_kmh")
        speeds.append(speed)
        if bb and len(bb) == 4:
            has_bbox += 1
        if bbox_ts:
            has_bbox_ts += 1
        clip = pkg.get("clip") or {}
        if clip.get("url") or clip.get("asset_id"):
            has_clip += 1
        for img in pkg.get("images") or []:
            if img.get("role") == "scene" and (img.get("url") or img.get("asset_id")):
                has_scene += 1
            if img.get("role") == "subject" and (img.get("url") or img.get("asset_id")):
                has_subject += 1
        status = pm.get("evidence_status", "?")
        print(f"  {a.get('created_at')} speed={speed} bbox_ts={'yes' if bbox_ts else 'NO'} evidence={status}")

    n = len(fresh)
    print(f"\nRésumé preuves sur {n} alertes fraîches:")
    print(f"  bbox valide     : {has_bbox}/{n}")
    print(f"  bbox_ts présent : {has_bbox_ts}/{n}")
    print(f"  clip            : {has_clip}/{n}")
    print(f"  scene           : {has_scene}/{n}")
    print(f"  subject (bbox)  : {has_subject}/{n}")
    if speeds:
        print(f"  vitesses        : {', '.join(str(s) for s in speeds[:8])}")

    print("\n=== ÉVÉNEMENTS speeding (DB) ===")
    print(psql(
        f"SELECT count(*) as events_since_marker FROM events WHERE camera_id='{CAM}' "
        f"AND event_type='speeding' AND occurred_at > '{MARKER}';"
    ))

    print("=== MAILHOG (3 derniers) ===")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8025/api/v2/messages?limit=5", timeout=5) as r:
            msgs = json.loads(r.read()).get("items", [])
        for m in msgs[:5]:
            subj = m.get("Content", {}).get("Headers", {}).get("Subject", ["?"])[0]
            print(f"  {m.get('Created')} | {subj}")
    except Exception as e:
        print(f"  mailhog: {e}")


if __name__ == "__main__":
    main()
