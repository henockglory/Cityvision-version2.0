#!/usr/bin/env python3
"""Quick speed demo diagnostic."""
import json
import subprocess
import sys
import urllib.request

API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
KEY = "changeme_internal_service_key"


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def main():
    login = get(
        API + "/api/v1/auth/login",
        {"Content-Type": "application/json"},
    ) if False else None
    body = json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode()
    login = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(API + "/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"})
        ).read()
    )
    tok = login["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    cams = get(f"{AI}/cameras")
    ligne = next((c for c in cams.get("cameras", []) if c["camera_id"] == CAM), {})
    print("=== AI camera ===")
    print(json.dumps(ligne, indent=2))

    sp = get(f"{AI}/cameras/{CAM}/spatial")
    print("\n=== AI spatial summary ===")
    print(json.dumps(sp, indent=2))

    dbg = get(
        f"{API}/api/v1/internal/ingest/orgs/{ORG}/cameras/{CAM}/spatial-config",
        {"X-Internal-Key": KEY},
    )
    print("\n=== Backend spatial-config ===")
    for z in dbg.get("zones", []):
        print(f"  zone={z.get('zone_id')} behavior={z.get('behavior')} limit={ (z.get('behavior_config') or {}).get('speed_limit_kmh') }")

    events = get(f"{API}/api/v1/orgs/{ORG}/events?limit=200", h)
    if not isinstance(events, list):
        events = events.get("items", [])
    by_cam = {}
    for e in events:
        cid = e.get("camera_id", "?")
        et = e.get("event_type") or e.get("type")
        by_cam.setdefault(cid, {}).setdefault(et, 0)
        by_cam[cid][et] += 1
    print("\n=== Events in API (all cameras) ===")
    for cid, counts in by_cam.items():
        print(cid[:8], counts)

    alerts = get(f"{API}/api/v1/orgs/{ORG}/alerts?limit=50", h)
    if not isinstance(alerts, list):
        alerts = alerts.get("items", [])
    print(f"\n=== Alerts count: {len(alerts)} ===")

    # DB direct
    q = (
        "SELECT event_type, count(*) FROM events "
        f"WHERE camera_id='{CAM}' AND created_at > now() - interval '24 hours' "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
    )
    out = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-c", q],
        capture_output=True,
        text=True,
    )
    print("\n=== DB events 24h (ligne) ===")
    print(out.stdout or out.stderr)


if __name__ == "__main__":
    main()
