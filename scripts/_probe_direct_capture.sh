#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

python3 <<'PY'
import json, urllib.request, time, os, urllib.error

# Probe AI capture directly with a synthetic speeding event using a fresh Frigate event timestamp
fc = "cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
cam = "55694d53-8f58-4981-91b2-7c6cd528a25d"
org = "74d51ead-97a7-4e41-a488-503a9b90c466"

evs = json.loads(urllib.request.urlopen(
    f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=1", timeout=8
).read())
assert evs, "no frigate events"
fe = evs[0]
print("frigate event", fe["id"], "start", fe["start_time"], "clip", fe.get("has_clip"), "snap", fe.get("has_snapshot"))

# Wait until clip downloadable
eid = fe["id"]
for i in range(20):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4", timeout=15) as r:
            n = len(r.read(2048))
            if n > 500:
                print(f"clip ready peek={n}")
                break
    except Exception as e:
        print(f"clip wait {i}: {e}")
    time.sleep(2)
else:
    print("WARN clip not ready, continuing anyway")

body = {
    "org_id": org,
    "event": {
        "event_id": f"probe-{int(time.time())}",
        "event_type": "speeding",
        "track_id": 999001,
        "class_name": "car",
        "bbox_ts": float(fe["start_time"]),
        "bbox": {"x": 0.3, "y": 0.4, "w": 0.15, "h": 0.2},
        "speed_kmh": 72.0,
        "frigate_event_id": eid,
    },
    "evidence": {
        "clip": True,
        "images": ["scene", "subject"],
        "plate": True,
    },
}
data = json.dumps(body).encode()
req = urllib.request.Request(
    f"http://127.0.0.1:8001/cameras/{cam}/evidence/capture",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST",
)
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.loads(resp.read().decode())
        print("CAPTURE_OK elapsed=%.1fs keys=%s" % (time.time()-t0, list(out.keys())[:12]))
        pkg = out.get("package") or out
        meta = pkg.get("metadata") if isinstance(pkg, dict) else {}
        if isinstance(meta, dict):
            print("capture_source=", meta.get("capture_source"))
            print("evidence_status=", out.get("evidence_status") or meta.get("evidence_status"))
            print("assets=", list((pkg.get("assets") or meta.get("assets") or {}).keys()) if isinstance(pkg, dict) else None)
        print(json.dumps({k: out.get(k) for k in ("evidence_status","s3_keys","clip_url","scene_url") if k in out}, indent=2)[:800])
except urllib.error.HTTPError as e:
    body = e.read().decode(errors="replace")
    print(f"CAPTURE_HTTP {e.code} elapsed={time.time()-t0:.1f}s body={body[:500]}")
except Exception as e:
    print(f"CAPTURE_ERR {e} elapsed={time.time()-t0:.1f}s")

print("--- recent frigate_track logs ---")
os.system("grep -n 'frigate_track\\|speed evidence\\|clip ok\\|clip unavailable\\|bound capture\\|reject' /home/gheno/citevision-v2/logs/ai-engine.log | tail -40")
PY
