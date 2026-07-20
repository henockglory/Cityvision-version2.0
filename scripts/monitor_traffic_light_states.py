#!/usr/bin/env python3
"""Monitor traffic_light_state on Feux camera for N seconds; print color transitions."""
from __future__ import annotations

import json
import os
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("paho-mqtt required", file=sys.stderr)
    raise SystemExit(1)

BROKER = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1884"))
SECONDS = int(sys.argv[1] if len(sys.argv) > 1 else 180)
FEUX = os.environ.get("DEMO_FEUX_CAMERA_ID", "726ff8a1-8442-4bdb-96ad-ec40a2fbb424")
TOPIC = "cv/events/#"

seen: list[str] = []
last_state: str | None = None
counts: dict[str, int] = {}


def on_message(_client, _userdata, msg):
    global last_state
    try:
        p = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        return
    cam = str(p.get("camera_id", ""))
    if FEUX not in cam and FEUX[:8] not in msg.topic:
        return
    et = p.get("event_type") or p.get("event") or ""
    if et != "traffic_light_state":
        return
    meta = p.get("metadata") or {}
    state = str(meta.get("state", "?"))
    counts[state] = counts.get(state, 0) + 1
    if state != last_state:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] traffic_light_state -> {state} (topic={msg.topic})")
        seen.append(state)
        last_state = state


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tl-monitor")
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.subscribe(TOPIC)
client.loop_start()
print(f"Listening {SECONDS}s on {TOPIC} for Feux {FEUX[:8]}…")
deadline = time.time() + SECONDS
while time.time() < deadline:
    time.sleep(1)
client.loop_stop()
client.disconnect()
print(f"\nTransitions: {' -> '.join(seen) if seen else '(none)'}")
print(f"Counts: {counts}")
if not seen:
    print("[WARN] No traffic_light_state MQTT events — check AI Feux ingest + Zone_des_feux")
    raise SystemExit(1)
colors = {s for s in seen if s in ("green", "amber", "red")}
if len(colors) >= 2:
    print(f"[OK] Saw {len(colors)} distinct colors: {sorted(colors)}")
else:
    print(f"[PARTIAL] Only saw: {sorted(colors or seen)}")
