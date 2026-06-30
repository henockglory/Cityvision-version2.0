#!/usr/bin/env python3
"""Synthetic red_light_violation MQTT → rules-engine → alert (no live video)."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import uuid

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("paho-mqtt required", file=sys.stderr)
    raise SystemExit(1)

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")
FEUX = os.environ.get("DEMO_FEUX_CAMERA_ID", "726ff8a1-8442-4bdb-96ad-ec40a2fbb424")
BROKER = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1884"))
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
RULE_NAME = "Démo · Feu rouge"
WAIT_SEC = int(os.environ.get("FEUX_ALERT_WAIT_SEC", "45"))
SYNC_WAIT = int(os.environ.get("RULE_SYNC_WAIT_SEC", "35"))


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def alert_meta(a: dict) -> dict:
    m = a.get("metadata") or {}
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except json.JSONDecodeError:
            m = {}
    return m


def count_demo_alerts(token: str) -> int:
    rows = req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=200&include_incomplete=true", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    return sum(
        1
        for a in rows
        if alert_meta(a).get("demo") is True
        or str(alert_meta(a).get("demo", "")).lower() == "true"
    )


def set_rules(token: str, rules: list[dict], enable_name: str | None) -> None:
    for r in rules:
        name = str(r.get("name", ""))
        if not name.startswith("Démo"):
            continue
        enabled = name == enable_name
        req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}", token, {"is_enabled": enabled})


def wait_active_rules(n: int, sec: int = 90) -> None:
    url = f"http://127.0.0.1:{os.environ.get('RULES_ENGINE_PORT', '8010')}/health"
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                active = int(json.loads(resp.read()).get("active_rules", -1))
            if active == n:
                print(f"active_rules={active}")
                return
        except Exception:
            pass
        time.sleep(3)
    print(f"WARN: active_rules != {n} after {sec}s")


def feu_camera_id(feu_rule: dict) -> str:
    definition = feu_rule.get("definition") or {}
    bindings = definition.get("bindings") or {}
    return str(definition.get("camera_id") or bindings.get("camera_id") or FEUX)


def main() -> int:
    print("==> test feux alert chain (synthetic MQTT)")
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", token)
    if not isinstance(rules, list):
        rules = []

    feu = next((r for r in rules if r.get("name") == RULE_NAME), None)
    if not feu:
        print(f"FAIL: rule {RULE_NAME!r} missing", file=sys.stderr)
        return 1

    camera_id = feu_camera_id(feu)
    baseline = count_demo_alerts(token)
    set_rules(token, rules, None)
    wait_active_rules(0, sec=120)
    time.sleep(SYNC_WAIT)

    set_rules(token, rules, RULE_NAME)
    wait_active_rules(1, sec=120)
    print(f"rules-engine sync wait {SYNC_WAIT}s…")
    time.sleep(SYNC_WAIT)

    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "org_id": ORG,
        "camera_id": camera_id,
        "event_type": "red_light_violation",
        "event": "red_light_violation",
        "timestamp": "2026-06-28T12:00:00Z",
        "track_id": 42,
        "class_name": "car",
        "confidence": 0.95,
        "severity": "high",
        "metadata": {"demo": True, "detection_method": "synthetic_test", "motion_px": 5.0},
    }
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="feux-alert-test")
    client.connect(BROKER, PORT, 60)
    client.publish(f"cv/events/{camera_id}", json.dumps(payload), qos=1)
    client.disconnect()
    print(f"published synthetic red_light_violation event_id={event_id[:8]}")

    deadline = time.time() + WAIT_SEC
    new_alerts = 0
    while time.time() < deadline:
        time.sleep(3)
        new_alerts = count_demo_alerts(token) - baseline
        if new_alerts >= 1:
            break

    set_rules(token, rules, None)
    wait_active_rules(0)

    if new_alerts >= 1:
        print(f"PASS — {new_alerts} demo alert(s) after synthetic event")
        return 0
    print(f"FAIL — no demo alert within {WAIT_SEC}s (delta={new_alerts})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
