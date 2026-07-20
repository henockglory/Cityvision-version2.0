#!/usr/bin/env python3
"""Inspect recent speeding events + alerts for camera 108."""
import json
import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / ".env", Path.home() / "citevision-v2" / ".env"):
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        break

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")
CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"


def psql(sql: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
        capture_output=True,
        text=True,
    )
    return proc.stdout or proc.stderr


def api(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body else None
    h = {"Content-Type": "application/json"} if body else {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


login = api("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
tok = login["access_token"]

print("=== Recent events cam108 (30 min) ===")
print(psql(
    f"SELECT occurred_at, event_type, payload->>'speed_kmh' as speed, payload->>'bbox_ts' as bbox_ts "
    f"FROM events WHERE camera_id='{CAM108}' AND occurred_at > now() - interval '30 minutes' "
    "ORDER BY occurred_at DESC LIMIT 10;"
))

print("\n=== Alerts with 108 in metadata or title (recent) ===")
print(psql(
    "SELECT created_at, title, status, metadata->>'camera_id' as meta_cam "
    "FROM alerts WHERE (title ILIKE '%vitesse%' OR title ILIKE '%speed%' OR metadata->>'camera_id'='" + CAM108 + "') "
    "ORDER BY created_at DESC LIMIT 10;"
))

print("\n=== API alerts recent (filter 108 in evidence) ===")
alerts = api("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=30&include_incomplete=true", tok)
if isinstance(alerts, dict):
    alerts = alerts.get("items", [])
for a in alerts[:10]:
    title = a.get("title", "")
    created = a.get("created_at", "")
    ev = a.get("evidence_snapshot") or a.get("evidence") or {}
    if isinstance(ev, str):
        try:
            ev = json.loads(ev)
        except json.JSONDecodeError:
            ev = {}
    pkg = ev.get("package", ev) if isinstance(ev, dict) else {}
    meta = pkg.get("metadata", {}) if isinstance(pkg, dict) else {}
    cam = meta.get("camera_id") or a.get("camera_id", "?")
    if "108" in str(cam) or "vitesse" in title.lower() or "speed" in title.lower():
        print(f"  {created} | {title[:50]} | cam={str(cam)[:8]} | status={meta.get('evidence_status')}")

print("\n=== Rules enabled for org ===")
print(psql(
    f"SELECT name, is_enabled FROM rules WHERE org_id='{ORG}' AND name ILIKE '%vitesse%' ORDER BY updated_at DESC;"
))
