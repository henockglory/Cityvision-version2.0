#!/usr/bin/env python3
"""Force 1 km/h speed limit, then observe 3 speeding events with full evidence + alerts + mail."""
from __future__ import annotations

import json
import subprocess
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
MAX_WAIT_SEC = 300


def get(url: str, headers: dict | None = None, data: bytes | None = None, timeout: float = 25):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else None


def login() -> str:
    body = json.dumps({"email": EMAIL, "password": PASS}).encode()
    return get(API + "/api/v1/auth/login", {"Content-Type": "application/json"}, body)["access_token"]


def evidence_ok(e: dict) -> tuple[bool, str]:
    snap = e.get("evidence_snapshot") or {}
    if isinstance(snap, str):
        snap = json.loads(snap) if snap else {}
    pkg = (snap.get("package") or {}) if isinstance(snap, dict) else {}
    clip = pkg.get("clip") or {}
    imgs = pkg.get("images") or []
    has_clip = bool(clip.get("url") or clip.get("asset_id"))
    has_imgs = len(imgs) >= 1
    payload = e.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload) if payload else {}
    ppkg = payload.get("package") or {}
    if not has_clip and isinstance(ppkg, dict):
        pc = ppkg.get("clip") or {}
        has_clip = bool(pc.get("url") or pc.get("asset_id"))
    if not has_imgs and isinstance(ppkg, dict):
        has_imgs = len(ppkg.get("images") or []) >= 1
    ok = has_clip and has_imgs
    detail = f"clip={has_clip} imgs={len(imgs) if imgs else len((ppkg.get('images') or []) if isinstance(ppkg, dict) else [])}"
    return ok, detail


def alert_evidence_ok(a: dict) -> tuple[bool, str]:
    snap = a.get("evidence_snapshot") or {}
    if isinstance(snap, str):
        snap = json.loads(snap) if snap else {}
    pkg = (snap.get("package") or {}) if isinstance(snap, dict) else {}
    clip = pkg.get("clip") or {}
    imgs = pkg.get("images") or []
    ok = bool(clip.get("url") or clip.get("asset_id")) and len(imgs) >= 1
    return ok, f"clip={bool(clip.get('url') or clip.get('asset_id'))} imgs={len(imgs)}"


def main() -> int:
    print("==> 1. Force speed limit 1 km/h + cooldown 5s")
    subprocess.run(
        ["bash", "-lc", "cd ~/citevision-v2 && DEMO_SPEED_LIMIT_KMH=1 bash scripts/fix-demo-speed-limit.sh"],
        check=False,
    )
    # Extra cooldown tweak (fix script may not set it)
    subprocess.run(
        [
            "bash", "-lc",
            "docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
            "\"UPDATE zones SET behavior_config = jsonb_set("
            "jsonb_set(COALESCE(behavior_config, '{}'::jsonb), '{config,cooldown_sec}', '5'), "
            "'{config,speed_limit_kmh}', '1') "
            "WHERE org_id = 'e312f375-7442-4089-8022-ed232abc09e8'::uuid "
            "AND name = 'Zone_distance_parcourue';\" && "
            "curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial "
            "-H \"X-Internal-Key: $(grep ^INTERNAL_API_KEY= ~/citevision-v2/.env | cut -d= -f2)\"",
        ],
        check=False,
    )
    time.sleep(15)

    tok = login()
    h = {"Authorization": f"Bearer {tok}"}

    try:
        sp = get(f"{AI}/cameras/{CAM}/spatial", timeout=10)
        print(f"AI spatial: zone_speed_active={sp.get('zone_speed_active')} behaviors={sp.get('behaviors')}")
    except Exception as exc:
        print(f"WARN AI spatial: {exc}")

    baseline_ids = set()
    try:
        ev0 = get(f"{API}/api/v1/orgs/{ORG}/events?limit=300&include_incomplete=true", h) or []
        baseline_ids = {e["id"] for e in ev0 if e.get("event_type") == "speeding" and e.get("camera_id") == CAM}
    except Exception:
        pass
    print(f"Baseline speeding events on ligne: {len(baseline_ids)}")

    print(f"\n==> 2. Poll up to {MAX_WAIT_SEC}s for {TARGET} new speeding + evidence + alerts")
    deadline = time.time() + MAX_WAIT_SEC
    seen_event_ids: set[str] = set()
    good_events: list[dict] = []
    good_alerts: list[dict] = []

    while time.time() < deadline and len(good_events) < TARGET:
        try:
            cams = get(f"{AI}/cameras", timeout=8)
            running = next(
                (c for c in (cams or {}).get("cameras", []) if c.get("camera_id") == CAM),
                {},
            )
            print(
                f"  AI ingest running={running.get('running')} frames={running.get('frames_processed')}",
                end="\r",
            )
        except Exception:
            pass

        events = get(f"{API}/api/v1/orgs/{ORG}/events?limit=300&include_incomplete=true", h) or []
        for e in events:
            eid = e.get("id", "")
            if e.get("event_type") != "speeding" or e.get("camera_id") != CAM:
                continue
            if eid in baseline_ids or eid in seen_event_ids:
                continue
            ev_ok, ev_det = evidence_ok(e)
            if not ev_ok:
                continue
            seen_event_ids.add(eid)
            good_events.append(e)
            payload = e.get("payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            spd = payload.get("speed_kmh") or (payload.get("metadata") or {}).get("speed_kmh")
            print(f"\n  [EVENT {len(good_events)}/{TARGET}] {e.get('occurred_at')} speed={spd} {ev_det}")

        alerts_raw = get(
            f"{API}/api/v1/orgs/{ORG}/alerts?limit=100&include_incomplete=true&status=open",
            h,
        )
        alerts = alerts_raw if isinstance(alerts_raw, list) else []
        for a in alerts:
            title = str(a.get("title", "")).lower()
            if "vitesse" not in title and a.get("camera_id") != CAM:
                continue
            aid = a.get("id", "")
            if any(x.get("id") == aid for x in good_alerts):
                continue
            al_ok, al_det = alert_evidence_ok(a)
            if al_ok:
                good_alerts.append(a)
                print(f"  [ALERT] {a.get('created_at')} {a.get('title')} {al_det}")

        if len(good_events) >= TARGET:
            break
        time.sleep(10)

    print(f"\n==> 3. Results: events={len(good_events)}/{TARGET} alerts_with_evidence={len(good_alerts)}")

    try:
        mh = get(MAILHOG, timeout=8)
        msgs = mh.get("items") or []
        speed_mails = [
            m for m in msgs
            if "vitesse" in json.dumps(m).lower() or "speed" in json.dumps(m).lower()
        ]
        print(f"MailHog messages total={len(msgs)} speed-related={len(speed_mails)}")
        for m in speed_mails[:5]:
            subj = (m.get("Content") or {}).get("Headers", {}).get("Subject", ["?"])[0]
            print(f"  mail: {subj}")
    except Exception as exc:
        print(f"MailHog: {exc}")

    re = get("http://127.0.0.1:8010/health", timeout=5)
    print(f"rules-engine active_rules={re.get('active_rules')}")

    if len(good_events) < TARGET:
        print(f"\nFAIL: only {len(good_events)} complete speeding events (need {TARGET})")
        subprocess.run(["bash", "-lc", "grep -E 'skip MQTT|evidence upload|speeding' ~/citevision-v2/logs/ai-engine.log | tail -15"], check=False)
        return 1

    print("\nOK: pipeline produced complete detections")
    for i, e in enumerate(good_events[:TARGET], 1):
        ev_ok, ev_det = evidence_ok(e)
        print(f"  #{i} event={e.get('id')[:8]}… evidence={ev_det}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
