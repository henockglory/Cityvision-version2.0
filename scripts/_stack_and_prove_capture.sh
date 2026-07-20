#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

# Backend
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  echo "restart backend"
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  free_port 8081
  if [[ ! -x "$ROOT/backend/bin/citevision-api" ]]; then
    (cd backend && "$GO_BIN" build -o bin/citevision-api ./cmd/api)
  fi
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok "http://127.0.0.1:8081/health" 90
fi
# AI
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh
fi
# Rules
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh
fi
# Frigate
if ! curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null; then
  docker start citevision-v2-go2rtc citevision-v2-frigate || true
  docker restart citevision-v2-go2rtc citevision-v2-frigate
  sleep 35
fi
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

python3 scripts/_reset_demo_password.py 'Hologram2026!'

# Disable demo rules to avoid storm; keep streams
python3 - <<'PY'
import json,urllib.request,time,subprocess
API="http://127.0.0.1:8081"; ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
login=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/auth/login",
  data=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode(),
  headers={"Content-Type":"application/json"}, method="POST")).read())
tok=login["access_token"]
rules=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules",
  headers={"Authorization":f"Bearer {tok}"})).read())
for r in rules:
  if str(r.get("name","")).startswith("Démo"):
    urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
      data=json.dumps({"is_enabled":False}).encode(),
      headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
vid="e774ae7a-137c-4c2f-901a-7324bb64c8b2"
urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/demo/settings",
  data=json.dumps({"source_mode":"video","active_video_id":vid,"active_camera_id":None}).encode(),
  headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
print("demo ready rules=off")
PY

# Wait fresh frigate
python3 - <<'PY'
import json,time,urllib.request
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
for i in range(24):
  ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=8).read())
  now=time.time()
  if isinstance(ev,list) and ev:
    young=min(now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float)))
    clip=any(e.get("has_clip") for e in ev)
    print(f"frigate young={young:.0f}s clip={clip} n={len(ev)}")
    if young<=45 and clip: break
  time.sleep(5)
PY

# Capture
python3 - <<'PY'
import json,urllib.request,time,subprocess
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",
  f"SELECT payload FROM events e WHERE e.camera_id='{CAM}'::uuid AND e.event_type='speeding' ORDER BY e.ingested_at DESC LIMIT 1;"],
  capture_output=True,text=True)
raw=(r.stdout or "").strip()
now=time.time()
evt=json.loads(raw) if raw else {"event_type":"speeding","event":"speeding","event_id":"manual","track_id":1,"camera_id":CAM,"org_id":ORG,"bbox":{"x":0.3,"y":0.3,"width":0.2,"height":0.2},"class_name":"car"}
evt["bbox_ts"]=now
evt["evidence_status"]="pending"
body={"org_id":ORG,"event":evt,"evidence":{"enabled":True,"clip_seconds":6,"images":[{"role":"scene"},{"role":"subject"},{"role":"plate"}]}}
print("capturing event", str(evt.get("event_id"))[:8])
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
try:
  with urllib.request.urlopen(req, timeout=240) as resp:
    data=json.loads(resp.read())
  pkg=data.get("package") or (data.get("evidence") or {}).get("package") or data
  meta=(pkg.get("metadata") or {}) if isinstance(pkg, dict) else {}
  print("OK evidence_status=", data.get("evidence_status") or meta.get("evidence_status"))
  print("capture_source=", meta.get("capture_source"))
  print("frigate_event_id=", meta.get("frigate_event_id"))
  print("clip=", bool(isinstance(pkg,dict) and pkg.get("clip")), "images=", len((pkg or {}).get("images") or []) if isinstance(pkg,dict) else 0)
  if meta.get("capture_source")!="frigate_track":
    raise SystemExit(3)
except Exception as e:
  print("FAIL", e)
  if hasattr(e,"read"): print(e.read()[:800])
  raise
PY

echo "=== logs ==="
grep -E 'frigate_track|dedupe|ERROR' "$ROOT/logs/ai-engine.log" | tail -30
echo "PROVE_OK"
