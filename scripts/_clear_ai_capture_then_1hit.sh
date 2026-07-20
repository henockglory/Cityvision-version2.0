#!/usr/bin/env bash
# Frigate already has record+fresh events. Clear AI storm, one capture, then 1-hit validate.
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
RULE='Démo · Excès de vitesse'

pkill -f '_validate_rule_frigate' 2>/dev/null || true

# Sync latest evidence code
for f in \
  ai-engine/src/citevision_ai/evidence/service.py \
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  ai-engine/src/citevision_ai/config.py \
  scripts/_validate_rule_frigate_1hit.py
do
  cp -f "/mnt/c/Users/gheno/citevision/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
done

# Pause rule to stop evidence/request storm while we restart AI
python3 scripts/_reset_demo_password.py 'Hologram2026!'
python3 - <<'PY'
import json,urllib.request
API="http://127.0.0.1:8081"; ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
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
print("rules paused")
PY

# Do NOT restart Frigate — keep young events + record
curl -sf http://127.0.0.1:5000/api/version >/dev/null || { echo "Frigate down"; exit 1; }
python3 - <<'PY'
import json,time,urllib.request
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3", timeout=8).read())
now=time.time()
young=min(now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float)))
print(f"frigate young={young:.0f}s clip={any(e.get('has_clip') for e in ev)} n={len(ev)}")
if young>90:
  raise SystemExit("frigate events too stale — re-run heal script")
PY

: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh

# Ensure camera ingest via demo settings
python3 - <<'PY'
import json,urllib.request,time
API="http://127.0.0.1:8081"; ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
login=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/auth/login",
  data=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode(),
  headers={"Content-Type":"application/json"}, method="POST")).read())
tok=login["access_token"]
urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/demo/settings",
  data=json.dumps({"source_mode":"video","active_video_id":"e774ae7a-137c-4c2f-901a-7324bb64c8b2","active_camera_id":None}).encode(),
  headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
time.sleep(10)
cams=json.loads(urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=10).read())
print("ai cams", cams)
PY

# One manual capture while rules OFF
python3 - <<'PY'
import json,urllib.request,time,subprocess
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",
  f"SELECT payload FROM events e WHERE e.camera_id='{CAM}'::uuid AND e.event_type='speeding' ORDER BY e.ingested_at DESC LIMIT 1;"],
  capture_output=True,text=True)
raw=(r.stdout or "").strip()
evt=json.loads(raw) if raw else {
  "event_type":"speeding","event_id":"manual-1hit","track_id":1,"camera_id":CAM,"org_id":ORG,
  "bbox":{"x":0.3,"y":0.3,"width":0.25,"height":0.25},"class_name":"car",
}
evt["bbox_ts"]=time.time(); evt["event_type"]="speeding"; evt["evidence_status"]="pending"
# unique event_id so cache doesn't confuse
evt["event_id"]=f"manual-{int(time.time())}"
body={"org_id":ORG,"event":evt,"evidence":{"enabled":True,"clip_seconds":6,"images":[{"role":"scene"},{"role":"subject"},{"role":"plate"}]}}
print("manual capture", evt["event_id"])
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
try:
  with urllib.request.urlopen(req, timeout=240) as resp:
    data=json.loads(resp.read())
except Exception as e:
  print("CAPTURE_HTTP_FAIL", e)
  if hasattr(e,"read"): print(e.read()[:1000])
  raise
pkg=data.get("package") or (data.get("evidence") or {}).get("package") or data
meta=(pkg.get("metadata") or {}) if isinstance(pkg, dict) else {}
print("status", data.get("evidence_status") or meta.get("evidence_status"))
print("src", meta.get("capture_source"), "fev", meta.get("frigate_event_id"))
print("clip", bool(isinstance(pkg,dict) and pkg.get("clip")),
      "images", len((pkg or {}).get("images") or []) if isinstance(pkg,dict) else 0)
print("=== AI log ===")
raise SystemExit(0 if meta.get("capture_source")=="frigate_track" and isinstance(pkg,dict) and pkg.get("clip") else 3)
PY

echo "MANUAL_CAPTURE_OK"
grep -E 'frigate_track|dedupe|ERROR' "$ROOT/logs/ai-engine.log" | tail -30

# Ensure rules-engine up, then run 1-hit validator (enables rule itself)
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh
fi

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Excès de vitesse'
export RULE_DURATION_SEC=600
export PYTHONUNBUFFERED=1
python3 scripts/_validate_rule_frigate_1hit.py
echo "VALIDATE_EXIT=$?"
