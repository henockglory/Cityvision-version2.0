#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

# Sync latest frigate_track_evidence
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/"*.py

# Keep backend up
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  bash /mnt/c/Users/gheno/citevision/scripts/_ensure_stack_speed.sh || true
fi

# Soft Frigate refresh: repair streams only (no docker restart unless needed)
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

python3 - <<'PY'
import json,time,urllib.request
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
for i in range(30):
  try:
    ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=8).read())
  except Exception as e:
    print("frigate err", e); time.sleep(5); continue
  now=time.time()
  if isinstance(ev,list) and ev:
    young=min(now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float)))
    print(f"young={young:.0f}s clip={any(e.get('has_clip') for e in ev)}")
    if young<=60: break
  time.sleep(5)
else:
  print("still stale — restart frigate once")
  import subprocess
  subprocess.run(["docker","restart","citevision-v2-frigate"], check=False)
  time.sleep(40)
  urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/api/v1/internal/demo/repair-streams",
    data=b"{}", headers={"X-Internal-Key":"changeme_internal_service_key","Content-Type":"application/json"}, method="POST"), timeout=60)
  time.sleep(20)
PY

: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh

# Disable rules
python3 scripts/_reset_demo_password.py 'Hologram2026!'
python3 - <<'PY'
import json,urllib.request
API="http://127.0.0.1:8081"; ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
login=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/auth/login",
  data=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode(),
  headers={"Content-Type":"application/json"}, method="POST")).read())
tok=login["access_token"]
rules=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules", headers={"Authorization":f"Bearer {tok}"})).read())
for r in rules:
  if str(r.get("name","")).startswith("Démo"):
    urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
      data=json.dumps({"is_enabled":False}).encode(),
      headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/demo/settings",
  data=json.dumps({"source_mode":"video","active_video_id":"e774ae7a-137c-4c2f-901a-7324bb64c8b2","active_camera_id":None}).encode(),
  headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
print("ready")
PY

sleep 8
bash /mnt/c/Users/gheno/citevision/scripts/_capture_now_stable.sh
