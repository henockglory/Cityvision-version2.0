#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOGDIR=$ROOT/logs

# Sync (idempotent)
cp -f "$WIN/ai-engine/src/citevision_ai/road_enforcement/traffic_light.py" \
  "$ROOT/ai-engine/src/citevision_ai/road_enforcement/traffic_light.py"
cp -f "$WIN/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
cp -f "$WIN/ai-engine/src/citevision_ai/pipeline.py" \
  "$ROOT/ai-engine/src/citevision_ai/pipeline.py"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' \
  "$ROOT/ai-engine/src/citevision_ai/road_enforcement/traffic_light.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "$ROOT/ai-engine/src/citevision_ai/pipeline.py" \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"

# Ensure markers in WSL copy (evidence quality + sticky-green guard — no zone rewrites)
grep -q 'raw_state == "red"' "$ROOT/ai-engine/src/citevision_ai/road_enforcement/traffic_light.py"
grep -q 'ignore stale bind for red_light' "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
grep -q 'abort red_light' "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
echo "markers_ok"

# Keep UI :5174 up for visual evidence review — never kill Vite during this test.
if ! curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null; then
  bash scripts/_sync_frontend_restart_wsl.sh || true
fi
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null && echo "UI :5174 up" || echo "UI :5174 DOWN"

# Health — restart AI only if code not loaded (always restart to be safe)
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh
fi
# Force reload of feu quality code
: > "$LOGDIR/ai-engine.log"
bash scripts/restart-ai-engine.sh
for i in $(seq 1 60); do curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
echo "AI up"

if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi
echo "backend up"
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi
echo "rules up"
curl -sf http://127.0.0.1:5000/api/version >/dev/null && echo "frigate up"
# Re-check UI after service restarts
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null && echo "UI still up" || {
  echo "UI dropped — restarting :5174"
  bash scripts/_sync_frontend_restart_wsl.sh || true
}

curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams >/dev/null || true
python3 scripts/_reset_demo_password.py 'Hologram2026!' || true

python3 <<'PY'
import json, urllib.request, time, urllib.error
fc="cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
ok=False
for i in range(30):
  try:
    ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5",timeout=8).read())
  except Exception as e:
    print("events_err", e); time.sleep(4); continue
  now=time.time()
  for e in (ev or []):
    # Clip only exists once Frigate has closed the event.
    if e.get("end_time") in (None, ""):
      continue
    age=now-float(e["start_time"])
    try:
      with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{e['id']}/clip.mp4",timeout=15) as r:
        n=len(r.read(2048))
      if n>500 and age<=300:
        print(f"media young={age:.0f}s peek={n}"); ok=True; break
      print(f"clip age={age:.0f} peek={n}")
    except Exception as ex:
      print(f"clip age={age:.0f} {ex}")
  if ok: break
  print(f"wait {i} n_ev={len(ev or [])}"); time.sleep(4)
assert ok, "feu frigate media not ready"
print("media_ready")
PY

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Feu rouge'
export RULE_DURATION_SEC=600
export SKIP_FRIGATE_REBUILD=1
export FRIGATE_MAX_ALIGN_MS=30000
export PYTHONUNBUFFERED=1
set +e
python3 scripts/_validate_rule_frigate_1hit.py
VC=$?
set -e
echo "VALIDATE_EXIT=$VC"

python3 <<'PY'
import json, urllib.request
from pathlib import Path
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
CAM="8ed20433-57d5-4999-a6ab-0bea028b23a3"
body=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode()
tok=json.loads(urllib.request.urlopen(urllib.request.Request(
  "http://127.0.0.1:8081/api/v1/auth/login",data=body,
  headers={"Content-Type":"application/json"},method="POST"),timeout=15).read())["access_token"]
h={"Authorization":f"Bearer {tok}"}
raw=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"http://127.0.0.1:8081/api/v1/orgs/{ORG}/alerts?limit=3&camera_id={CAM}",headers=h),timeout=20).read())
items=raw if isinstance(raw,list) else raw.get("alerts") or raw.get("items") or []
for a in items[:3]:
  snap=a.get("evidence_snapshot") or {}
  pkg=snap.get("package") or {}
  meta=pkg.get("metadata") or {}
  print(f"alert {str(a.get('id',''))[:8]} src={meta.get('capture_source')} bbox_src={meta.get('bbox_source')} "
        f"bbox_ok={meta.get('bbox_quality_ok')} subject_ok={meta.get('subject_quality_ok')} "
        f"texture={meta.get('subject_texture')} align={meta.get('align_delta_ms')}")
log=Path("/home/gheno/citevision-v2/logs/ai-engine.log").read_text(errors="replace")
for n in ("ignore stale bind for red_light","abort red_light","reject IoU","red_dominates"):
  print(f"log '{n}': {log.count(n)}")
PY
exit $VC
