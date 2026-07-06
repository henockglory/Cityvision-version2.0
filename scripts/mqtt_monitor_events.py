#!/usr/bin/env python3
"""Subscribe to cv/events/# and print traffic/speed events for N seconds."""
from __future__ import annotations

import json
import sys
import time

import paho.mqtt.client as mqtt

WATCH = {"traffic_light_state", "red_light_violation", "speeding", "line_cross", "seatbelt_violation"}
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 45


def main() -> int:
    seen: list[str] = []

    def on_msg(_c: mqtt.Client, _u: object, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return
        et = payload.get("event_type") or payload.get("event") or ""
        if et not in WATCH:
            return
        seen.append(et)
        meta = payload.get("metadata") or {}
        print(f"{msg.topic} {et} {meta}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_msg
    client.connect("127.0.0.1", 1884)
    client.subscribe("cv/events/#")
    client.loop_start()
    print(f"Listening {DURATION}s on cv/events/# …")
    time.sleep(DURATION)
    client.loop_stop()
    print("TOTAL", seen)
    return 0 if seen else 1


if __name__ == "__main__":
    raise SystemExit(main())
