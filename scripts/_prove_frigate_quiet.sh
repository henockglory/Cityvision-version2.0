#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
FCAM=cv_55694d53-8f58-4981-91b2-7c6cd528a25d
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d

pkill -f '_validate_rule_frigate' 2>/dev/null || true

# Sync code
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/config.py "$ROOT/ai-engine/src/citevision_ai/config.py"
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/service.py" "$ROOT/ai-engine/src/citevision_ai/config.py"
grep -q 'dedupe skip (retro)' "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"

# Ensure frigate healthy + streams + fresh events
if ! curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null; then
  docker restart citevision-v2-go2rtc citevision-v2-frigate
  sleep 35
fi
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

echo "=== wait frigate fresh with clip ==="
python3 - <<PY
import json,time,urllib.request
fc="$FCAM"
ok=False
for i in range(36):
    try:
        ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=8).read())
    except Exception as e:
        print("err", e); time.sleep(5); continue
    now=time.time()
    if isinstance(ev,list) and ev:
        young=min(now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float)))
        clip=any(e.get("has_clip") for e in ev)
        print(f"try {i} n={len(ev)} young={young:.0f}s clip={clip}")
        if young<=40 and clip:
            ok=True; break
    else:
        print(f"try {i} empty")
    time.sleep(5)
print("FRESH", "OK" if ok else "FAIL")
raise SystemExit(0 if ok else 2)
PY

: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh

# Disable speed rule briefly so no storm during manual capture, then enable after
python3 scripts/_reset_demo_password.py 'Hologram2026!' >/dev/null
python3 - <<'PY'
import json,urllib.request,time,subprocess
API="http://127.0.0.1:8081"; ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; RULE="Démo · Excès de vitesse"
CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
login=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/auth/login",
  data=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode(),
  headers={"Content-Type":"application/json"}, method="POST")).read())
tok=login["access_token"]
rules=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules",
  headers={"Authorization":f"Bearer {tok}"})).read())
# disable all demo during manual
for r in rules:
  if str(r.get("name","")).startswith("Démo"):
    urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
      data=json.dumps({"is_enabled":False}).encode(),
      headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
print("rules off")
# ensure camera registered via demo settings
vid="e774ae7a-137c-4c2f-901a-7324bb64c8b2"
urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/demo/settings",
  data=json.dumps({"source_mode":"video","active_video_id":vid,"active_camera_id":None}).encode(),
  headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
time.sleep(8)
# Build synthetic event from latest frigate-ish fields using last DB speeding or minimal
r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",
  f"SELECT payload FROM events e WHERE e.camera_id='{CAM}'::uuid AND e.event_type='speeding' ORDER BY e.ingested_at DESC LIMIT 1;"],
  capture_output=True,text=True)
raw=(r.stdout or "").strip()
import time as t
now=t.time()
if raw:
  evt=json.loads(raw)
else:
  evt={"event_type":"speeding","event":"speeding","event_id":"manual-test","track_id":1,"camera_id":CAM,"org_id":ORG,"bbox":{"x":0.3,"y":0.3,"width":0.2,"height":0.2},"class_name":"car"}
evt["bbox_ts"]=now
evt["evidence_status"]="pending"
evt["event_id"]=evt.get("event_id") or "manual-test"
body={"org_id":ORG,"event":evt,"evidence":{"enabled":True,"clip_seconds":6,"images":[{"role":"scene"},{"role":"subject"},{"role":"plate"}]}}
print("manual capture…")
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
try:
  with urllib.request.urlopen(req, timeout=240) as resp:
    data=json.loads(resp.read())
  print("HTTP 200")
  pkg=data.get("package") or (data.get("evidence") or {}).get("package") or data
  meta=(pkg.get("metadata") or {}) if isinstance(pkg, dict) else {}
  print("status", data.get("evidence_status"), "src", meta.get("capture_source"), "fev", meta.get("frigate_event_id"))
  print("clip", bool(isinstance(pkg,dict) and pkg.get("clip")), "images", len((pkg or {}).get("images") or []) if isinstance(pkg,dict) else 0)
except Exception as e:
  print("FAIL", e)
  if hasattr(e,"read"): print(e.read()[:500])
PY

echo "=== logs ==="
grep -E 'dedupe|frigate_track|retroactive|ERROR' "$ROOT/logs/ai-engine.log" | tail -40
