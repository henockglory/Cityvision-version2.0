#!/usr/bin/env python3
"""Publish a synthetic traffic_light_state and verify DB ingest."""
from __future__ import annotations

import json
import subprocess
import time
import uuid

import paho.mqtt.client as mqtt

ORG = "e312f375-7442-4089-8022-ed232abc09e8"
FEUX = "726ff8a1-8442-4bdb-96ad-ec40a2fbb424"
EVENT_ID = str(uuid.uuid4())


def main() -> None:
    payload = {
        "event_id": EVENT_ID,
        "camera_id": FEUX,
        "event_type": "traffic_light_state",
        "event": "traffic_light_state",
        "timestamp": "2026-06-29T14:30:00Z",
        "track_id": -1,
        "severity": "info",
        "metadata": {"state": "red", "detection_method": "synthetic_test"},
    }
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect("127.0.0.1", 1884)
    client.publish(f"cv/events/{FEUX}", json.dumps(payload), qos=1)
    client.disconnect()
    print("published", EVENT_ID)
    time.sleep(3)
    subprocess.run(
        [
            "docker",
            "exec",
            "citevision-v2-postgres",
            "psql",
            "-U",
            "citevision",
            "-d",
            "citevision",
            "-c",
            f"SELECT event_type, payload->>'event_id' FROM events WHERE payload->>'event_id' = '{EVENT_ID}';",
        ],
        check=False,
    )


if __name__ == "__main__":
    main()
