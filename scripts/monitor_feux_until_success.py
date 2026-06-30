#!/usr/bin/env python3
"""Monitor Feux camera until red_light_violation OR all 3 traffic-light colors seen."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("paho-mqtt required", file=sys.stderr)
    raise SystemExit(1)

BROKER = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1884"))
MAX_SEC = int(os.environ.get("FEUX_MONITOR_MAX_SEC", "600"))
FEUX = os.environ.get("DEMO_FEUX_CAMERA_ID", "726ff8a1-8442-4bdb-96ad-ec40a2fbb424")
AI = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8001")
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
TOPIC = "cv/events/#"
TARGET_COLORS = {"green", "amber", "red"}
RULE_NAME = "Démo · Feu rouge"


def api_req(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def count_demo_alerts(token: str) -> int:
    rows = api_req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=200", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    n = 0
    for a in rows:
        m = a.get("metadata") or {}
        if isinstance(m, str):
            try:
                m = json.loads(m)
            except json.JSONDecodeError:
                m = {}
        if m.get("demo") is True or str(m.get("demo", "")).lower() == "true":
            n += 1
    return n


def enable_feux_rule() -> int:
    login = api_req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    rules = api_req("GET", f"{API}/api/v1/orgs/{ORG}/rules", token)
    if not isinstance(rules, list):
        rules = []
    baseline = count_demo_alerts(token)
    for r in rules:
        name = str(r.get("name", ""))
        if not name.startswith("Démo"):
            continue
        enabled = name == RULE_NAME
        api_req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}", token, {"is_enabled": enabled})
    print(f"[with-rule] enabled {RULE_NAME!r}, demo alerts baseline={baseline}")
    time.sleep(15)
    return baseline


def feux_match(cam: str, topic: str) -> bool:
    return FEUX in cam or FEUX[:8] in topic


def run_monitor(max_sec: int, with_rule: bool) -> int:
    colors_seen: set[str] = set()
    transitions: list[str] = []
    last_color: str | None = None
    violations: list[dict] = []
    done_reason: str | None = None
    alerts_before = 0

    if with_rule:
        alerts_before = enable_feux_rule()

    def seed_live_color() -> None:
        nonlocal last_color
        try:
            with urllib.request.urlopen(f"{AI}/cameras/{FEUX}/spatial", timeout=8) as resp:
                sp = json.loads(resp.read().decode())
            st = str(sp.get("traffic_light_state") or "").lower()
            if st in TARGET_COLORS:
                colors_seen.add(st)
                last_color = st
                print(f"[seed] AI spatial current color: {st}")
        except Exception as exc:
            print(f"[seed] skip AI spatial: {exc}")

    def check_done() -> bool:
        nonlocal done_reason
        if violations:
            done_reason = f"red_light_violation x{len(violations)}"
            return True
        if TARGET_COLORS.issubset(colors_seen):
            done_reason = f"3 colors seen: {sorted(colors_seen & TARGET_COLORS)}"
            return True
        return False

    def on_message(_client, _userdata, msg):
        nonlocal last_color, done_reason
        if done_reason:
            return
        try:
            p = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            return
        cam = str(p.get("camera_id", ""))
        if not feux_match(cam, msg.topic):
            return
        et = p.get("event_type") or p.get("event") or ""
        ts = time.strftime("%H:%M:%S")

        if et == "traffic_light_state":
            meta = p.get("metadata") or {}
            state = str(meta.get("state", "")).lower()
            if state in TARGET_COLORS:
                colors_seen.add(state)
                if state != last_color:
                    print(f"[{ts}] traffic_light_state -> {state}")
                    transitions.append(state)
                    last_color = state
            check_done()

        elif et == "red_light_violation":
            meta = p.get("metadata") or {}
            violations.append(
                {
                    "track_id": p.get("track_id"),
                    "class": p.get("class_name"),
                    "motion_px": meta.get("motion_px"),
                }
            )
            print(
                f"[{ts}] red_light_violation track={p.get('track_id')} "
                f"class={p.get('class_name')} motion={meta.get('motion_px')}"
            )
            check_done()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="feux-until-ok")
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.subscribe(TOPIC)
    client.loop_start()

    seed_live_color()
    print(f"Monitor Feux {FEUX[:8]} — stop on violation OR green+amber+red (max {max_sec}s)")
    start = time.time()
    deadline = start + max_sec
    while time.time() < deadline and not done_reason:
        time.sleep(0.5)

    client.loop_stop()
    client.disconnect()
    elapsed = int(time.time() - start)

    if with_rule and violations:
        try:
            login = api_req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
            delta = count_demo_alerts(login["access_token"]) - alerts_before
            print(f"[with-rule] demo alerts delta after violation: {delta}")
        except Exception as exc:
            print(f"[with-rule] alert check failed: {exc}")

    print("\n--- Summary ---")
    print(f"Elapsed: {elapsed}s")
    print(f"Colors: {sorted(colors_seen & TARGET_COLORS)} / {sorted(TARGET_COLORS)}")
    print(f"Transitions: {' -> '.join(transitions) if transitions else '(none)'}")
    print(f"Violations: {len(violations)}")
    if violations:
        print(f"  last: {violations[-1]}")

    if done_reason:
        print(f"\nPASS — {done_reason}")
        report = {
            "status": "PASS",
            "reason": done_reason,
            "elapsed_s": elapsed,
            "colors": sorted(colors_seen & TARGET_COLORS),
            "transitions": transitions,
            "violations": len(violations),
        }
        out = os.environ.get("FEUX_REPORT_JSON", "")
        if out:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        return 0

    print(f"\nFAIL — timeout {max_sec}s without violation or 3 colors")
    print(f"  missing colors: {sorted(TARGET_COLORS - colors_seen)}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Feux traffic-light MQTT events")
    parser.add_argument(
        "max_sec",
        nargs="?",
        type=int,
        default=None,
        help="Max seconds (overrides FEUX_MONITOR_MAX_SEC)",
    )
    parser.add_argument(
        "--with-rule",
        action="store_true",
        help="Enable feu demo rule and report alert delta if violation seen",
    )
    args = parser.parse_args()
    max_sec = args.max_sec if args.max_sec is not None else MAX_SEC
    return run_monitor(max_sec, args.with_rule)


if __name__ == "__main__":
    raise SystemExit(main())
