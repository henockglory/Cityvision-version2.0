#!/usr/bin/env bash
# Sync fixes, restart AI, validate counting then red_light.
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
mkdir -p logs
LOG="$ROOT/logs/validate-after-speedonly-fix.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== START $(date -Is) ==="

for f in \
  ai-engine/src/citevision_ai/pipeline.py \
  scripts/_validate_rule_frigate_1hit.py \
  scripts/validate_rule_dod.py \
  scripts/validate_rule.sh
do
  cp -f "$WIN/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
done

echo "=== restart AI ==="
bash scripts/_restart_ai.py 2>/dev/null || bash scripts/_restart_ai_proper.sh 2>/dev/null || {
  pkill -f 'uvicorn citevision_ai.main:app' || true
  sleep 2
  cd ai-engine
  nohup .venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port 8001 > /tmp/citevision-ai.log 2>&1 &
  cd "$ROOT"
}
for i in $(seq 1 60); do
  curl -sf http://127.0.0.1:8001/health >/dev/null && break
  sleep 2
done
curl -sf http://127.0.0.1:8001/health | head -c 200; echo

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo

# quick live prove counting
echo "=== prove line_cross 60s ==="
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
CAM=9a3cd323-3820-46f0-aa5b-86c086a4a782
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=(name='Démo · Comptage véhicules') WHERE org_id='$ORG'::uuid AND name LIKE 'Démo%';"
TOKEN=$(curl -sf -X POST http://127.0.0.1:8081/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"'"${ADMIN_EMAIL:-glory.henock@hologram.cd}"'","password":"'"${ADMIN_PASSWORD:-Hologram2026!}"'"}' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -sf -X PATCH "http://127.0.0.1:8081/api/v1/orgs/$ORG/demo/settings" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"source_mode":"video","active_video_id":"1a7dd0c0-1557-427c-9a9e-03da850561d9","active_camera_id":null}' >/dev/null
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo
curl -sf -X POST http://127.0.0.1:8010/internal/sync-rules; echo
sleep 15
echo "AI spatial:"; curl -sf http://127.0.0.1:8001/cameras/$CAM/spatial; echo
BEFORE=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT coalesce(sum(count_total),0) FROM line_counters WHERE camera_id='$CAM'::uuid AND line_id='Ligne_count';")
SINCE=$(date -u +'%Y-%m-%d %H:%M:%S+00')
echo "counter_before=$BEFORE"
sleep 45
AFTER=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT coalesce(sum(count_total),0) FROM line_counters WHERE camera_id='$CAM'::uuid AND line_id='Ligne_count';")
EV=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT count(*) FROM events WHERE camera_id='$CAM'::uuid AND event_type='line_cross' AND ingested_at>='$SINCE'::timestamptz;")
echo "counter_after=$AFTER events=$EV"
if [[ "${EV:-0}" -lt 1 && "${AFTER:-0}" -le "${BEFORE:-0}" ]]; then
  echo "WARN counting still silent — continue validate anyway"
fi

# Ensure UI + OCR + frigate
curl -sf http://127.0.0.1:5174/ >/dev/null || (cd frontend && nohup npm run dev -- --host 127.0.0.1 --port 5174 >/tmp/citevision-vite.log 2>&1 &)
curl -sf http://127.0.0.1:8181/healthz >/dev/null || (cd infra && docker compose --env-file "$ROOT/.env" --profile ocr up -d citevision-ocr)
# Frigate up
timeout 4 curl -sf http://127.0.0.1:5000/api/version || docker restart citevision-v2-frigate
for i in $(seq 1 40); do timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null && break; sleep 2; done

export RULE_DURATION_SEC=360
export VALIDATE_MODE=wait
export SKIP_FRIGATE_REBUILD=1

echo "########## COUNTING $(date -Is) ##########"
bash scripts/validate_rule.sh counting
echo EC_count=$?

echo "########## RED_LIGHT $(date -Is) ##########"
# Heal frigate gently before red (needs record + fresh events)
bash scripts/ensure-demo-streams.sh || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams; echo
# Wait for ANY fresh frigate events globally before starting
python3 - <<'PY'
import json,time,urllib.request
ok=False
for i in range(40):
  try:
    with urllib.request.urlopen('http://127.0.0.1:5000/api/events?limit=10', timeout=8) as r:
      ev=json.loads(r.read().decode())
    now=time.time()
    ages=[now-float(e['start_time']) for e in ev if e.get('start_time')]
    young=min(ages) if ages else 9999
    print(f'  frigate young={young:.0f}s n={len(ev)}', flush=True)
    if young<=30:
      ok=True; break
  except Exception as e:
    print('  err', e, flush=True)
  time.sleep(3)
print('FRESH', ok)
PY
bash scripts/validate_rule.sh red_light
echo EC_red=$?

echo "=== FINAL SCORECARD ==="
for a in speeding red_light phone seatbelt counting; do
  latest=$(find validation-evidence/$a -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "${latest:-}" ]]; then
    python3 -c "import json,os;d=json.load(open('$latest'));print(d.get('result'), '$a', 'ui='+str(os.path.exists(os.path.join(os.path.dirname('$latest'),'ui.png'))))"
  else
    echo "NONE $a"
  fi
done
echo "=== DONE $(date -Is) ==="
