#!/usr/bin/env python3
"""Set speed rule to 1 km/h, resync spatial, observe 3 complete detections."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
MAILHOG = "http://127.0.0.1:8025/api/v2/messages"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"
TARGET = 3
MAX_WAIT = 360


def load_internal_key() -> str:
    for path in (os.path.expanduser("~/citevision-v2/.env"), "/mnt/c/Users/gheno/citevision/.env"):
        if os.path.isfile(path):
            for line in open(path):
                if line.startswith("INTERNAL_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return "changeme_internal_service_key"


def req(method: str, url: str, headers: dict | None = None, body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers or {})
    if body is not None:
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else None


def evidence_complete(obj: dict, snap_key: str = "evidence_snapshot") -> tuple[bool, str]:
    snap = obj.get(snap_key) or {}
    if isinstance(snap, str):
        snap = json.loads(snap) if snap else {}
    pkg = (snap.get("package") or {}) if isinstance(snap, dict) else {}
    clip = pkg.get("clip") or {}
    imgs = pkg.get("images") or []
    has_clip = bool(clip.get("url") or clip.get("asset_id"))
    has_imgs = len(imgs) >= 2 or (len(imgs) >= 1 and has_clip)
    return has_clip and len(imgs) >= 1, f"clip={has_clip} imgs={len(imgs)}"


def main() -> int:
    key = load_internal_key()
    print("==> 1. PATCH rule speed_kmh=1 + zone cooldown 5s")
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    tok = login["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", h)
    speed_rule = next(r for r in rules if "Excès de vitesse" in r.get("name", ""))
    defn = speed_rule.get("definition") or {}
    bindings = dict(defn.get("bindings") or {})
    bindings["speed_kmh"] = 1
    defn["bindings"] = bindings
    req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{speed_rule['id']}", h, {"definition": defn, "is_enabled": True})
    print(f"   rule patched id={speed_rule['id'][:8]}… speed_kmh=1")

    # Zone cooldown via internal resync path (orchestrator reads rules)
    req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", headers={"X-Internal-Key": key})
    print("   resync-spatial OK")

    # Invalidate + wait orchestrator push (~35s)
    time.sleep(35)

    sp_cfg = req(
        "GET",
        f"{API}/api/v1/internal/ingest/orgs/{ORG}/cameras/{CAM}/spatial-config",
        {"X-Internal-Key": key},
    )
    for z in sp_cfg.get("zones", []):
        if z.get("behavior") == "speed_measurement":
            bc = z.get("behavior_config") or {}
            print(f"   AI config: speed_limit_kmh={bc.get('speed_limit_kmh')} cooldown={bc.get('cooldown_sec')}")

    sp = req("GET", f"{AI}/cameras/{CAM}/spatial", timeout=15)
    print(f"   AI live: zone_speed_active={sp.get('zone_speed_active')}")

    events_before = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=500&include_incomplete=true", h) or []
    baseline = {e["id"] for e in events_before if e.get("event_type") == "speeding" and e.get("camera_id") == CAM}
    alerts_before = req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=200&include_incomplete=true", h) or []
    if not isinstance(alerts_before, list):
        alerts_before = []
    baseline_alerts = {a["id"] for a in alerts_before}

    print(f"\n==> 2. Poll {MAX_WAIT}s for {TARGET} new speeding events WITH evidence")
    good_events: list[dict] = []
    good_alerts: list[dict] = []
    deadline = time.time() + MAX_WAIT

    while time.time() < deadline and len(good_events) < TARGET:
        try:
            cams = req("GET", f"{AI}/cameras", timeout=10)
            cam = next((c for c in (cams or {}).get("cameras", []) if c.get("camera_id") == CAM), {})
            print(f"   frames={cam.get('frames_processed')} running={cam.get('running')}", end="\r")
        except Exception:
            pass

        events = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=500&include_incomplete=true", h) or []
        for e in events:
            if e.get("id") in baseline or e.get("event_type") != "speeding" or e.get("camera_id") != CAM:
                continue
            ok, det = evidence_complete(e)
            if not ok:
                continue
            if any(x["id"] == e["id"] for x in good_events):
                continue
            payload = e.get("payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            spd = payload.get("speed_kmh")
            good_events.append(e)
            print(f"\n   EVENT #{len(good_events)} {e.get('occurred_at')} speed={spd} {det}")

        alerts = req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=200&include_incomplete=true", h) or []
        if not isinstance(alerts, list):
            alerts = []
        for a in alerts:
            if a.get("id") in baseline_alerts:
                continue
            if "vitesse" not in str(a.get("title", "")).lower():
                continue
            ok, det = evidence_complete(a)
            if ok and not any(x["id"] == a["id"] for x in good_alerts):
                good_alerts.append(a)
                print(f"   ALERT {a.get('title')} {det}")

        if len(good_events) >= TARGET:
            break
        time.sleep(12)

    print(f"\n==> 3. Summary events={len(good_events)}/{TARGET} alerts={len(good_alerts)}")
    try:
        mh = req("GET", MAILHOG, timeout=8)
        recent = (mh or {}).get("items") or []
        print(f"   MailHog total={len(recent)}")
    except Exception as exc:
        print(f"   MailHog: {exc}")

    if len(good_events) < TARGET:
        print("FAIL — check AI log for skip MQTT / evidence upload")
        return 1
    print("OK — reload http://localhost:5174/demo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
