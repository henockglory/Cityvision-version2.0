#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== restart AI clean ==="
: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh
for i in $(seq 1 45); do
  if curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then echo AI_OK; break; fi
  sleep 2
done

# backend may die
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  source scripts/lib/env-utils.sh
  ENV_FILE="$(ensure_env_file "$ROOT")"
  load_dotenv "$ENV_FILE"
  LOGDIR=$ROOT/logs
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi

python3 <<'PY'
import json, urllib.request, time, urllib.error, traceback

cam = "55694d53-8f58-4981-91b2-7c6cd528a25d"
org = "74d51ead-97a7-4e41-a488-503a9b90c466"
fc = "cv_" + cam

# Ensure camera started
try:
    req = urllib.request.Request(f"http://127.0.0.1:8001/cameras/{cam}/start", method="POST", data=b"{}")
    urllib.request.urlopen(req, timeout=10).read()
    print("camera start ok")
except Exception as e:
    print("camera start", e)

evs = json.loads(urllib.request.urlopen(
    f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3", timeout=8
).read())
print("events", len(evs))
fe = evs[0]
eid = fe["id"]
print("using", eid, "age", time.time()-float(fe["start_time"]))

# wait clip
for i in range(15):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4", timeout=15) as r:
            if len(r.read(2048)) > 500:
                print("clip ok")
                break
    except Exception as e:
        print("clip", i, e)
    time.sleep(2)

def try_capture(label, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8001/cameras/{cam}/evidence/capture",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            out = json.loads(resp.read().decode())
            print(f"[{label}] OK {time.time()-t0:.1f}s status={out.get('evidence_status')} keys={list(out)[:8]}")
            pkg = out.get("package") or {}
            meta = (pkg.get("metadata") if isinstance(pkg, dict) else {}) or {}
            print(f"  capture_source={meta.get('capture_source')} meta_keys={list(meta)[:12]}")
            return out
    except urllib.error.HTTPError as e:
        print(f"[{label}] HTTP {e.code} {time.time()-t0:.1f}s {e.read().decode()[:300]}")
    except Exception as e:
        print(f"[{label}] ERR {time.time()-t0:.1f}s {e}")

# 1) with bound frigate id
try_capture("bound", {
    "org_id": org,
    "event": {
        "event_id": f"probe-bound-{int(time.time())}",
        "event_type": "speeding",
        "track_id": 424242,
        "class_name": "car",
        "bbox_ts": float(fe["start_time"]),
        "bbox": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.25},
        "speed_kmh": 80,
        "frigate_event_id": eid,
    },
    "evidence": {"clip": True, "images": [{"role": "scene"}, {"role": "subject"}], "plate": True},
})

# 2) without bound id — pure correlate
try_capture("correlate", {
    "org_id": org,
    "event": {
        "event_id": f"probe-corr-{int(time.time())}",
        "event_type": "speeding",
        "track_id": 424243,
        "class_name": "car",
        "bbox_ts": time.time(),
        "bbox": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.25},
        "speed_kmh": 80,
    },
    "evidence": {"clip": True, "images": [{"role": "scene"}, {"role": "subject"}], "plate": True},
})

print("--- AI log ---")
import pathlib
log = pathlib.Path("/home/gheno/citevision-v2/logs/ai-engine.log").read_text(errors="replace")
for n in ("speed evidence", "frigate_track", "clip ok", "bound capture", "no correlated", "retroactive semaphore", "capture unavailable", "404"):
    print(f"  {n}: {log.count(n)}")
for line in log.splitlines():
    if any(x in line for x in ("frigate_track", "speed evidence", "clip ok", "bound", "ERROR", "Traceback", "retro")):
        print(line)
PY
