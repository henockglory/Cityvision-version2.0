#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
grep -q 'brief wait for any vehicle' "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" && echo "fallback wait synced"

: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh

python3 scripts/_reset_demo_password.py 'Hologram2026!' || echo "pwd reset fail $?"

python3 - <<'PY'
import json,urllib.request,time,subprocess,traceback
API="http://127.0.0.1:8081"; ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
try:
  login=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/auth/login",
    data=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode(),
    headers={"Content-Type":"application/json"}, method="POST"), timeout=30).read())
  tok=login["access_token"]
  print("login ok")
  rules=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules",
    headers={"Authorization":f"Bearer {tok}"}), timeout=30).read())
  for r in rules:
    if str(r.get("name","")).startswith("Démo"):
      urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
        data=json.dumps({"is_enabled":False}).encode(),
        headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"), timeout=30)
  print("rules disabled")
  vid="e774ae7a-137c-4c2f-901a-7324bb64c8b2"
  urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/demo/settings",
    data=json.dumps({"source_mode":"video","active_video_id":vid,"active_camera_id":None}).encode(),
    headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"), timeout=60)
  print("demo on")
except Exception:
  traceback.print_exc(); raise

# repair streams + wait frigate
import os
key=os.environ.get("INTERNAL_API_KEY","changeme_internal_service_key")
try:
  urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/api/v1/internal/demo/repair-streams",
    data=b"{}", headers={"X-Internal-Key":key,"Content-Type":"application/json"}, method="POST"), timeout=60)
except Exception as e:
  print("repair warn", e)
time.sleep(10)

# freshest frigate event age
fc="cv_"+CAM
ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3", timeout=8).read())
now=time.time()
print("frigate events", [(e.get("id","")[:18], round(now-float(e["start_time"]),1), e.get("has_clip"), e.get("label")) for e in ev])

r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",
  f"SELECT payload FROM events e WHERE e.camera_id='{CAM}'::uuid AND e.event_type='speeding' ORDER BY e.ingested_at DESC LIMIT 1;"],
  capture_output=True,text=True)
raw=(r.stdout or "").strip()
now=time.time()
if raw:
  evt=json.loads(raw)
else:
  evt={"event_type":"speeding","event":"speeding","event_id":"manual-test","track_id":1,"camera_id":CAM,"org_id":ORG,
       "bbox":{"x":0.3,"y":0.3,"width":0.2,"height":0.2},"class_name":"car"}
evt["bbox_ts"]=now
evt["evidence_status"]="pending"
body={"org_id":ORG,"event":evt,"evidence":{"enabled":True,"clip_seconds":6,"images":[{"role":"scene"},{"role":"subject"},{"role":"plate"}]}}
print("capture start", "event_id", str(evt.get("event_id"))[:8])
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
try:
  with urllib.request.urlopen(req, timeout=240) as resp:
    data=json.loads(resp.read())
  print("HTTP", resp.status)
  pkg=data.get("package") or (data.get("evidence") or {}).get("package") or data
  meta=(pkg.get("metadata") or {}) if isinstance(pkg, dict) else {}
  print("evidence_status", data.get("evidence_status") or meta.get("evidence_status"))
  print("capture_source", meta.get("capture_source"))
  print("frigate_event_id", meta.get("frigate_event_id"))
  print("clip", bool(isinstance(pkg,dict) and pkg.get("clip")), "images", len((pkg or {}).get("images") or []) if isinstance(pkg,dict) else 0)
except Exception as e:
  print("CAPTURE_FAIL", e)
  if hasattr(e,"read"): print(e.read()[:800])
PY

echo "=== logs ==="
grep -E 'dedupe|frigate_track|retroactive|ERROR|Exception' "$ROOT/logs/ai-engine.log" | tail -50
