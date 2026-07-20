#!/usr/bin/env bash
# Sync red-light soft-accept + force Frigate rebuild, restart AI, validate red_light only.
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
mkdir -p logs
LOG="$ROOT/logs/validate-red-soft-iou.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== START $(date -Is) ==="

# Stop leftover validate if any
pkill -f '_validate_rule_frigate_1hit|validate_rule.sh red' 2>/dev/null || true
sleep 2

for f in \
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  scripts/_validate_rule_frigate_1hit.py \
  scripts/validate_rule_dod.py \
  scripts/validate_rule.sh
do
  cp -f "$WIN/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
done

echo "=== restart AI with OCR ==="
bash scripts/_restart_ai.py || true
for i in $(seq 1 40); do curl -sf http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:8081/health >/dev/null || bash scripts/_restart_backend.sh
curl -sf http://127.0.0.1:8010/health >/dev/null || bash scripts/_start-rules-engine.sh
curl -sf http://127.0.0.1:8181/healthz >/dev/null || (cd infra && docker compose --env-file "$ROOT/.env" --profile ocr up -d citevision-ocr)
curl -sf http://127.0.0.1:5174/ >/dev/null || (cd frontend && nohup npm run dev -- --host 127.0.0.1 --port 5174 >/tmp/citevision-vite.log 2>&1 &)

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo

export RULE_DURATION_SEC=480
export VALIDATE_MODE=wait
# Do NOT skip rebuild — red needs record aggregate
unset SKIP_FRIGATE_REBUILD

echo "########## RED_LIGHT $(date -Is) ##########"
bash scripts/validate_rule.sh red_light
echo EC_red=$?

echo "=== SCORECARD ==="
for a in speeding red_light phone seatbelt counting; do
  latest=$(find validation-evidence/$a -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "${latest:-}" ]]; then
    python3 -c "import json,os;d=json.load(open('$latest'));print(d.get('result'), '$a', 'ui='+str(os.path.exists(os.path.join(os.path.dirname('$latest'),'ui.png'))))"
  else
    echo "NONE $a"
  fi
done
echo "=== DONE $(date -Is) ==="
