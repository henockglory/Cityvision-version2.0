#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

pkill -f '_validate_rule_frigate_1hit.py' 2>/dev/null || true
pkill -f '_deploy_and_run_speed_1hit' 2>/dev/null || true

# Sync latest service/config
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/config.py \
  "$ROOT/ai-engine/src/citevision_ai/config.py"
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/service.py" \
  "$ROOT/ai-engine/src/citevision_ai/config.py"

# Shorter correlate wait so slots free faster
upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ROOT/.env"; then sed -i "s|^${key}=.*|${key}=${val}|" "$ROOT/.env"
  else printf '%s=%s\n' "$key" "$val" >>"$ROOT/.env"; fi
}
upsert FRIGATE_CORRELATE_WAIT_SEC 12
upsert FRIGATE_DEMO_MAX_ALIGN_SEC 10
upsert FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC 10

: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh

# Ensure backend + frigate
curl -sf http://127.0.0.1:8081/health >/dev/null || {
  GO_BIN=/usr/local/go/bin/go
  stop_from_pid "$ROOT/logs/backend.pid" 2>/dev/null || true
  free_port 8081
  (cd backend && "$GO_BIN" build -o bin/citevision-api ./cmd/api)
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok "http://127.0.0.1:8081/health" 90
}
if ! curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
  docker restart citevision-v2-go2rtc citevision-v2-frigate
  sleep 35
fi
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

# Enable speed rule + rebuild so record stays on
python3 scripts/_reset_demo_password.py 'Hologram2026!'
python3 - <<'PY'
import json,urllib.request
API="http://127.0.0.1:8081"; ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; RULE="Démo · Excès de vitesse"
login=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/auth/login",
  data=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode(),
  headers={"Content-Type":"application/json"}, method="POST")).read())
tok=login["access_token"]
rules=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules",
  headers={"Authorization":f"Bearer {tok}"})).read())
rule=next(r for r in rules if r.get("name")==RULE)
cam=None
defn=rule.get("definition") or {}
if isinstance(defn,str): defn=json.loads(defn)
cam=defn.get("camera_id") or (defn.get("bindings") or {}).get("camera_id")
for r in rules:
  name=str(r.get("name",""))
  if name.startswith("Démo"):
    urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
      data=json.dumps({"is_enabled": name==RULE}).encode(),
      headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
# activate demo video for speed cam
cams=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/cameras",
  headers={"Authorization":f"Bearer {tok}"})).read())
vid=None
for c in cams if isinstance(cams,list) else cams.get("cameras",[]):
  if str(c.get("id"))==str(cam):
    meta=c.get("metadata") or {}
    if isinstance(meta,str): meta=json.loads(meta)
    vid=meta.get("demo_video_id"); break
print("cam", cam, "vid", vid)
urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/demo/settings",
  data=json.dumps({"source_mode":"video","active_video_id":vid,"active_camera_id":None}).encode(),
  headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
print("demo switched")
PY

curl -sS -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true
sleep 5
# Confirm record
python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
m=re.search(rf"{re.escape(cam)}:.*?record:\s*\n\s*enabled:\s*(true|false)", text, re.S)
print("record", m.group(1) if m else "?")
assert m and m.group(1)=="true"
PY

# Wait for AI to have camera frames + frigate fresh
sleep 15
curl -sf http://127.0.0.1:8001/cameras | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d)'

# Wait one speeding event then capture
python3 - <<'PY'
import json, time, subprocess, urllib.request
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
deadline=time.time()+180
evt=None
while time.time()<deadline:
    r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",
      f"SELECT payload FROM events e JOIN cameras c ON c.id=e.camera_id WHERE c.org_id='{ORG}'::uuid AND e.event_type='speeding' AND e.ingested_at>now()-interval '30 seconds' ORDER BY e.ingested_at DESC LIMIT 1;"],
      capture_output=True,text=True)
    raw=(r.stdout or "").strip()
    if raw:
        evt=json.loads(raw); print("got event", evt.get("event_id"), "track", evt.get("track_id")); break
    print("waiting speeding event..."); time.sleep(5)
if not evt:
    raise SystemExit("no speeding event")
# Use live bbox_ts
evt["bbox_ts"]=time.time()
body={"org_id":ORG,"event":evt,"evidence":{"enabled":True,"clip_seconds":6,"images":[{"role":"scene"},{"role":"subject"},{"role":"plate"}]}}
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
print("capturing...")
with urllib.request.urlopen(req, timeout=240) as resp:
    data=json.loads(resp.read())
print("RESULT keys", list(data.keys()))
pkg=data.get("package") or (data.get("evidence") or {}).get("package") or data
if isinstance(pkg, dict):
    meta=pkg.get("metadata") or {}
    print("capture_source", meta.get("capture_source"))
    print("frigate_event_id", meta.get("frigate_event_id"))
    print("evidence_status", data.get("evidence_status") or meta.get("evidence_status"))
    imgs=pkg.get("images") or []
    print("images", len(imgs), "clip", bool(pkg.get("clip")))
else:
    print(data)
PY

echo "=== logs ==="
grep -E 'dedupe|frigate_track|ERROR|Exception' "$ROOT/logs/ai-engine.log" | tail -40
