#!/usr/bin/env bash
set -euo pipefail
# Direct capture with correlate (no bound id) after clean AI restart — prove fallback path
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh
sleep 5
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done

# Ensure backend up
if ! curl -sf http://127.0.0.1:8081/health >/dev/null; then
  source scripts/lib/env-utils.sh
  ENV_FILE="$(ensure_env_file "$ROOT")"
  load_dotenv "$ENV_FILE"
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 60
fi

python3 <<'PY'
import json, urllib.request, time, urllib.error, os

cam = "55694d53-8f58-4981-91b2-7c6cd528a25d"
org = "74d51ead-97a7-4e41-a488-503a9b90c466"
fc = "cv_" + cam

# What does AI think about frigate?
import pathlib
# check env inside process via a tiny endpoint if any — else read .env
env = {}
for line in open("/home/gheno/citevision-v2/.env"):
    line=line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    k,v=line.split("=",1); env[k]=v.strip().strip('"').strip("'")
print("FRIGATE_BASE_URL", env.get("FRIGATE_BASE_URL") or env.get("FRIGATE_URL"))
print("DEMO_MODE", env.get("DEMO_MODE"))
print("DEMO_EVIDENCE_BACKEND", env.get("DEMO_EVIDENCE_BACKEND"))

evs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=1", timeout=8).read())
fe = evs[0]
print("fresh event", fe["id"], "age", time.time()-float(fe["start_time"]))
# wait clip
for i in range(12):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{fe['id']}/clip.mp4", timeout=15) as r:
            if len(r.read(2048))>500:
                print("clip ready"); break
    except Exception as e:
        print("clip", e)
    time.sleep(2)

body = {
    "org_id": org,
    "event": {
        "event_id": f"corr-{int(time.time())}",
        "event_type": "speeding",
        "track_id": 777001,
        "class_name": "car",
        "bbox_ts": time.time(),  # wall clock — may not match frigate
        "bbox": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.25},
        "speed_kmh": 88,
    },
    "evidence": {"clip": True, "images": [{"role":"scene"},{"role":"subject"}], "plate": True},
}
req = urllib.request.Request(
    f"http://127.0.0.1:8001/cameras/{cam}/evidence/capture",
    data=json.dumps(body).encode(),
    headers={"Content-Type":"application/json"},
    method="POST",
)
t0=time.time()
try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        out=json.loads(resp.read().decode())
        meta=(out.get("package") or {}).get("metadata") or {}
        print(f"OK {time.time()-t0:.1f}s src={meta.get('capture_source')} status={out.get('evidence_status') or meta.get('evidence_status')}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} {time.time()-t0:.1f}s {e.read().decode()[:400]}")

# second call should reuse
body["event"]["event_id"] = f"corr2-{int(time.time())}"
body["event"]["track_id"] = 777002
req = urllib.request.Request(
    f"http://127.0.0.1:8001/cameras/{cam}/evidence/capture",
    data=json.dumps(body).encode(),
    headers={"Content-Type":"application/json"},
    method="POST",
)
t0=time.time()
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        out=json.loads(resp.read().decode())
        meta=(out.get("package") or {}).get("metadata") or {}
        print(f"REUSE OK {time.time()-t0:.1f}s src={meta.get('capture_source')} status={out.get('evidence_status') or meta.get('evidence_status')}")
except urllib.error.HTTPError as e:
    print(f"REUSE HTTP {e.code} {time.time()-t0:.1f}s {e.read().decode()[:400]}")

log=open("/home/gheno/citevision-v2/logs/ai-engine.log").read()
print("--- log snippets ---")
for line in log.splitlines():
    if any(x in line for x in ("frigate_track", "speed evidence", "ERROR", "Traceback", "WARNING:citevision_ai.evidence")):
        print(line)
PY
