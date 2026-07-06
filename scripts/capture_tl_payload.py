#!/usr/bin/env python3
import json
import time

import paho.mqtt.client as mqtt

seen = []


def on_msg(_c, _u, msg):
    try:
        p = json.loads(msg.payload)
    except json.JSONDecodeError:
        return
    if p.get("event_type") == "traffic_light_state":
        seen.append(p)
        print(json.dumps(p, indent=2))


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.on_message = on_msg
c.connect("127.0.0.1", 1884)
c.subscribe("cv/events/726ff8a1-8442-4bdb-96ad-ec40a2fbb424")
c.loop_start()
print("waiting for traffic_light_state …")
t0 = time.time()
while time.time() - t0 < 120 and len(seen) < 2:
    time.sleep(0.5)
c.loop_stop()
print("captured", len(seen))
