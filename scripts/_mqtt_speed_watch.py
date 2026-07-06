#!/usr/bin/env python3
import json, sys, time
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("no paho"); sys.exit(1)

seen = []

def on_message(_c, _u, msg):
    try:
        p = json.loads(msg.payload)
    except Exception:
        return
    et = p.get("event_type") or p.get("event")
    if et != "speeding":
        return
    pkg = p.get("package") or (p.get("evidence") or {}).get("package")
    seen.append(p)
    print(
        f"MQTT speeding speed={p.get('speed_kmh')} limit={p.get('speed_limit_kmh')} "
        f"package={bool(pkg)} topic={msg.topic}"
    )

cl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
cl.on_message = on_message
cl.connect("127.0.0.1", 1884)
cl.subscribe("cv/events/#")
cl.loop_start()
sec = int(sys.argv[1]) if len(sys.argv) > 1 else 90
print(f"Listening {sec}s...")
time.sleep(sec)
cl.loop_stop()
print(f"total speeding mqtt={len(seen)}")
