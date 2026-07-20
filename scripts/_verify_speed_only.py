"""Verify speed-only camera: low MQTT noise + speeding events."""
import urllib.request, json, time, sys
from collections import Counter

BASE = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
CAM = "55694d53-8f58-4981-91b2-7c6cd528a25d"

def login():
    body = json.dumps({"email": "glory.henock@hologram.cd", "password": "Henockglory@03"}).encode()
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["access_token"]

def main():
    token = login()
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Resync spatial (rebuild rules without loitering on speed zones)
    req = urllib.request.Request(
        f"{BASE}/api/v1/internal/ingest/resync-spatial",
        data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=30).read()
        print("resync-spatial: OK")
    except Exception as e:
        print("resync-spatial:", e)

    # Demo heal
    patch = urllib.request.Request(
        f"{BASE}/api/v1/orgs/{ORG}/demo/settings",
        data=b"{}", headers=hdrs, method="PATCH"
    )
    urllib.request.urlopen(patch, timeout=30).read()
    print("demo PATCH: OK")
    time.sleep(15)

    # FPS check
    d1 = json.loads(urllib.request.urlopen(f"{AI}/cameras", timeout=10).read())
    time.sleep(5)
    d2 = json.loads(urllib.request.urlopen(f"{AI}/cameras", timeout=10).read())
    for c1, c2 in zip(d1["cameras"], d2["cameras"]):
        if c1["camera_id"].startswith("55694d53"):
            fps = (c2["frames_processed"] - c1["frames_processed"]) / 5
            print(f"FPS eff: {fps:.1f}, drops={c2['frames_dropped']}")

    # MQTT event types
    import paho.mqtt.client as mqtt
    types = Counter()
    def on_msg(c, u, m):
        try:
            d = json.loads(m.payload)
            types[d.get("event_type") or d.get("event", "??")] += 1
        except Exception:
            types["bad_json"] += 1
    client = mqtt.Client()
    client.on_message = on_msg
    client.connect("127.0.0.1", 1884)
    client.subscribe(f"cv/events/{CAM}")
    client.loop_start()
    time.sleep(12)
    client.loop_stop()
    print("MQTT events (12s on demo cam):")
    for k, v in types.most_common(10):
        print(f"  {k}: {v}")
    noise = sum(v for k, v in types.items() if k not in ("speeding", "??"))
    print(f"Noise events: {noise}, speeding: {types.get('speeding', 0)}")

if __name__ == "__main__":
    main()
