#!/usr/bin/env python3
"""Monitor feu bridge emission stats during video loop."""
import json
import time
import urllib.request

AI = "http://127.0.0.1:8001"
CAM = "8ed20433-57d5-4999-a6ab-0bea028b23a3"
DURATION = 180


def fetch():
    with urllib.request.urlopen(f"{AI}/debug/rule-blockers", timeout=10) as r:
        return json.loads(r.read().decode())


print(f"monitor feu emit {DURATION}s", flush=True)
t0 = time.time()
last = {}
while time.time() - t0 < DURATION:
    d = fetch()
    fb = d.get("frigate_bridge") or {}
    hsv = (d.get("hsv_gate_debug") or {}).get(CAM) or {}
    mqtt = (fb.get("mqtt_by_camera") or {}).get(CAM, 0)
    keys = (
        "lf_or_g_emitted", "lf_or_g_would_emit", "red_light_enqueued",
        "red_light_skipped_not_red", "red_light_skipped_not_raw_red",
        "red_light_skipped_frigate_snapshot_not_red", "red_light_memory_enqueued",
        "red_light_poll_events",
    )
    snap = {k: fb.get(k, 0) for k in keys}
    delta = {k: snap[k] - last.get(k, 0) for k in keys}
    last = snap
    print(
        f"t+{int(time.time()-t0):3d}s gate={hsv.get('gate')} raw={hsv.get('raw')} "
        f"mqtt={mqtt} lf_emit={snap['lf_or_g_emitted']}(+{delta['lf_or_g_emitted']}) "
        f"lf_would={snap['lf_or_g_would_emit']}(+{delta['lf_or_g_would_emit']}) "
        f"skip_not_red={snap['red_light_skipped_not_red']}(+{delta['red_light_skipped_not_red']}) "
        f"snap_not_red={snap['red_light_skipped_frigate_snapshot_not_red']}(+{delta['red_light_skipped_frigate_snapshot_not_red']})",
        flush=True,
    )
    time.sleep(8)
