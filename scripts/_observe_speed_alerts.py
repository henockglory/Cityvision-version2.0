#!/usr/bin/env python3
"""Observe speeding detections vs alerts after fixes."""
import json
import subprocess
import urllib.request
from datetime import datetime, timezone

API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"


def get(url, headers=None, data=None):
    hdrs = dict(headers or {})
    body = data.encode() if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, headers=hdrs)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else None


def main():
    login = get(
        API + "/api/v1/auth/login",
        {"Content-Type": "application/json"},
        data=json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}),
    )
    tok = login["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    sp = get(f"{AI}/cameras/{CAM}/spatial")
    print("=== AI spatial ===")
    print(f"zone_speed_active={sp.get('zone_speed_active')} zones={sp.get('zone_count')}")

    events = get(f"{API}/api/v1/orgs/{ORG}/events?limit=200&include_incomplete=true", h) or []
    speed = [
        e
        for e in events
        if (e.get("event_type") or e.get("type")) == "speeding" and e.get("camera_id") == CAM
    ]
    print(f"\n=== Speeding events (ligne): {len(speed)} ===")
    for e in speed[:10]:
        payload = e.get("payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        meta = payload.get("metadata") or {}
        ts = e.get("occurred_at") or e.get("timestamp") or "?"
        print(
            f"  {ts} speed={payload.get('speed_kmh') or meta.get('speed_kmh')} "
            f"method={meta.get('detection_method')} track={payload.get('track_id')}"
        )

    alerts = get(
        f"{API}/api/v1/orgs/{ORG}/alerts?limit=50&include_incomplete=true&status=open",
        h,
    )
    if alerts is None:
        alerts = []
    print(f"\n=== Open alerts: {len(alerts)} ===")
    for a in alerts[:10]:
        print(f"  {a.get('created_at')} {a.get('title')} rule={a.get('rule_name')}")

    re_health = get("http://127.0.0.1:8010/health")
    print(f"\n=== rules-engine active_rules={re_health.get('active_rules')} ===")

    out = subprocess.run(
        ["grep", "-E", "alert suppressed|PublishAlert|matched rule", "/home/gheno/citevision-v2/logs/rules-engine.log"],
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in (out.stdout or "").strip().split("\n") if ln][-12:]
    print("\n=== rules-engine log (recent) ===")
    for ln in lines:
        print(" ", ln[-140:])


if __name__ == "__main__":
    main()
