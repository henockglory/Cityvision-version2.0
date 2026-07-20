#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR=$ROOT/logs
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
GO_BIN=/usr/local/go/bin/go
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

ensure_backend() {
  if curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then return 0; fi
  echo "starting backend…"
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  free_port 8081
  [[ -x backend/bin/citevision-api ]] || (cd backend && "$GO_BIN" build -o bin/citevision-api ./cmd/api)
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
}

ensure_ai() {
  if curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
    curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json;d=json.load(sys.stdin);assert d.get("models_all_ok") in (True,"true","True")'
    return 0
  fi
  bash scripts/restart-ai-engine.sh
}

ensure_backend
ensure_ai

# Frigate must be up with young events
curl -sf http://127.0.0.1:5000/api/version >/dev/null
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
python3 - <<'PY'
import json,time,urllib.request
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
for i in range(24):
  ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=8).read())
  now=time.time()
  young=min(now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float))) if ev else 9999
  print(f"frigate young={young:.0f}s n={len(ev) if isinstance(ev,list) else 0}")
  if young<=40: break
  time.sleep(5)
else:
  raise SystemExit("no young frigate events")
PY

# Register camera via internal resync (no login)
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial || true
sleep 8
curl -sf http://127.0.0.1:8001/cameras | python3 -m json.tool | head -40

# Direct capture — no login needed
python3 - <<'PY'
import json,urllib.request,time,subprocess
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",
  f"SELECT payload FROM events e WHERE e.camera_id='{CAM}'::uuid AND e.event_type='speeding' ORDER BY e.ingested_at DESC LIMIT 1;"],
  capture_output=True,text=True)
raw=(r.stdout or "").strip()
evt=json.loads(raw) if raw else {
  "event_type":"speeding","track_id":1,"camera_id":CAM,"org_id":ORG,
  "bbox":{"x":0.3,"y":0.3,"width":0.25,"height":0.25},"class_name":"car",
}
evt["bbox_ts"]=time.time(); evt["event_type"]="speeding"; evt["evidence_status"]="pending"
evt["event_id"]=f"manual-{int(time.time())}"
body={"org_id":ORG,"event":evt,"evidence":{"enabled":True,"clip_seconds":6,"images":[{"role":"scene"},{"role":"subject"},{"role":"plate"}]}}
print("capturing", evt["event_id"])
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
try:
  with urllib.request.urlopen(req, timeout=240) as resp:
    data=json.loads(resp.read())
except Exception as e:
  print("FAIL", e)
  if hasattr(e,"read"): print(e.read()[:1500])
  raise SystemExit(2)
pkg=data.get("package") or (data.get("evidence") or {}).get("package") or data
meta=(pkg.get("metadata") or {}) if isinstance(pkg, dict) else {}
print("status", data.get("evidence_status") or meta.get("evidence_status"))
print("src", meta.get("capture_source"), "fev", meta.get("frigate_event_id"))
print("clip", bool(isinstance(pkg,dict) and pkg.get("clip")),
      "images", len((pkg or {}).get("images") or []) if isinstance(pkg,dict) else 0)
open("/tmp/cv_capture.json","w").write(json.dumps({"status":data.get("evidence_status"),"meta":meta}, default=str))
ok = meta.get("capture_source")=="frigate_track" and isinstance(pkg,dict) and bool(pkg.get("clip"))
print("CAPTURE", "OK" if ok else "FAIL")
raise SystemExit(0 if ok else 3)
PY

echo "=== logs ==="
grep -E 'frigate_track|dedupe|ERROR|Exception' "$ROOT/logs/ai-engine.log" | tail -40
