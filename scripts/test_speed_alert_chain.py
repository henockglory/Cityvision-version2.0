#!/usr/bin/env python3
"""Synthetic speeding MQTT → rules-engine → alert (validates demo alert policy)."""
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
LIGNE = os.environ.get("DEMO_LIGNE_CAMERA_ID", "01ee632c-271c-4e66-ba98-3d1d7e430c09")
BROKER = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1884"))
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
RULE_NAME = "Démo · Excès de vitesse"
WAIT_SEC = int(os.environ.get("SPEED_ALERT_WAIT_SEC", "45"))
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


def speed_alerts(token: str) -> list[dict]:
    rows = req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=200&include_incomplete=true&status=open", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    return [a for a in rows if "vitesse" in str(a.get("title", "")).lower()]


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


def main() -> int:
    print("==> test speed alert chain (synthetic MQTT)")
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", token)
    if not isinstance(rules, list):
        rules = []

    speed_rule = next((r for r in rules if r.get("name") == RULE_NAME), None)
    if not speed_rule:
        print(f"FAIL: rule {RULE_NAME!r} missing", file=sys.stderr)
        return 1

    baseline = len(speed_alerts(token))
    set_rules(token, rules, RULE_NAME)
    wait_active_rules(1, sec=120)
    print(f"rules-engine sync wait {SYNC_WAIT}s…")
    time.sleep(SYNC_WAIT)

    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "org_id": ORG,
        "camera_id": LIGNE,
        "event_type": "speeding",
        "event": "speeding",
        "timestamp": "2026-07-01T14:00:00Z",
        "track_id": 99,
        "zone_id": "Zone_distance_parcourue",
        "class_name": "car",
        "speed_kmh": 15.8,
        "confidence": 0.9,
        "severity": "high",
        "demo": True,
        "metadata": {
            "demo": True,
            "speed_kmh": 15.8,
            "speed_limit_kmh": 8,
            "detection_method": "synthetic_test",
        },
        "package": {
            "clip": {"url": "http://127.0.0.1:9000/citevision-evidence/demo/speed-test.mp4"},
            "images": [
                {"role": "scene", "url": "http://127.0.0.1:9000/citevision-evidence/demo/scene.jpg"},
            ],
        },
    }
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER, PORT, 60)
    topic = f"cv/events/{LIGNE}"
    client.publish(topic, json.dumps(payload), qos=1)
    client.disconnect()
    print(f"published synthetic speeding event_id={event_id}")

    deadline = time.time() + WAIT_SEC
    while time.time() < deadline:
        rows = speed_alerts(token)
        if len(rows) > baseline:
            a = rows[0]
            print(f"OK alert created: {a.get('title')} id={a.get('id')}")
            return 0
        time.sleep(2)

    print("FAIL: no speed alert after synthetic MQTT", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
