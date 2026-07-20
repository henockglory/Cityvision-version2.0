#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"

cp -f "$WIN/ai-engine/src/citevision_ai/evidence/service.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
cp -f "$WIN/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
cp -f "$WIN/ai-engine/src/citevision_ai/config.py" \
  "$ROOT/ai-engine/src/citevision_ai/config.py"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' \
  "$ROOT/ai-engine/src/citevision_ai/evidence/"*.py \
  "$ROOT/ai-engine/src/citevision_ai/config.py" \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"

"$ROOT/ai-engine/.venv/bin/python" - <<'PY'
from pathlib import Path
t = Path("ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py").read_text()
assert "demo_mode and settings.frigate_demo_timeline_align" in t
assert "visual plate proof" in t or "plaque si disponible" in t
c = Path("ai-engine/src/citevision_ai/config.py").read_text()
assert "frigate_demo_accept_max_align_sec: float = 20" in c
print("correlation+plate fixes present")
PY

source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOGDIR=$ROOT/logs

: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh
for i in $(seq 1 45); do curl -sf http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done

if ! curl -sf http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi
if ! curl -sf http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

echo "=== direct HTTP capture (correlate) ==="
python3 <<'PY'
import json, urllib.request, time, urllib.error
cam="55694d53-8f58-4981-91b2-7c6cd528a25d"
org="74d51ead-97a7-4e41-a488-503a9b90c466"
fc="cv_"+cam
ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=1",timeout=8).read())[0]
eid=ev["id"]
for i in range(15):
  try:
    with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4",timeout=15) as r:
      if len(r.read(2048))>500: print("clip ready"); break
  except Exception as e:
    print("clip", e)
  time.sleep(2)
body={"org_id":org,"event":{
  "event_id":f"http-{int(time.time())}","event_type":"speeding","track_id":9001,
  "class_name":"car","bbox_ts":float(ev["start_time"]),
  "bbox":{"x":0.3,"y":0.4,"w":0.2,"h":0.25},"speed_kmh":90,
  "frigate_event_id": eid,
},"evidence":{"clip":True,"clip_seconds":6,"images":[
  {"role":"scene","label":"Vue"},{"role":"subject","label":"Cible"},{"role":"plate","label":"Plaque","crop":"plate"}
]}}
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{cam}/evidence/capture",
  data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST")
t0=time.time()
try:
  out=json.loads(urllib.request.urlopen(req,timeout=180).read())
  pkg=out.get("package") or {}
  meta=pkg.get("metadata") or {}
  imgs=pkg.get("images") or []
  roles=[(i.get("role"), bool(i.get("url") or i.get("asset_id"))) for i in imgs if isinstance(i,dict)]
  clip=pkg.get("clip") or {}
  print(f"OK {time.time()-t0:.1f}s src={meta.get('capture_source')} status={out.get('evidence_status') or meta.get('evidence_status')}")
  print(f"  roles={roles} clip={bool(clip.get('url') or clip.get('asset_id'))} plate_number={meta.get('plate_number')}")
except urllib.error.HTTPError as e:
  print(f"HTTP {e.code} {time.time()-t0:.1f}s {e.read().decode()[:400]}")
PY

python3 scripts/_reset_demo_password.py 'Hologram2026!' || true
export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Excès de vitesse'
export TARGET_DETECTIONS=1
export RULE_DURATION_SEC=360
export SKIP_FRIGATE_REBUILD=1
export PYTHONUNBUFFERED=1
echo "=== validate ==="
python3 scripts/_validate_rule_frigate_1hit.py
echo "VALIDATE_EXIT=$?"
