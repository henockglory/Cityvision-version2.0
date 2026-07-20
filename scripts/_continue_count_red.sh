#!/usr/bin/env bash
# Re-audit counting (1hit already PASS) + full red_light validate.
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
mkdir -p logs
LOG="$ROOT/logs/validate-count-red-continue.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== START $(date -Is) ==="

for f in \
  scripts/validate_rule_dod.py \
  scripts/_validate_rule_frigate_1hit.py \
  scripts/validate_rule.sh \
  ai-engine/src/citevision_ai/pipeline.py
do
  cp -f "$WIN/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
done

# Ensure stack bits
curl -sf http://127.0.0.1:8081/health >/dev/null || bash scripts/_restart_backend.sh
curl -sf http://127.0.0.1:8010/health >/dev/null || bash scripts/_start-rules-engine.sh
curl -sf http://127.0.0.1:8001/health >/dev/null || bash scripts/_restart_ai.py
curl -sf http://127.0.0.1:5174/ >/dev/null || (cd frontend && nohup npm run dev -- --host 127.0.0.1 --port 5174 >/tmp/citevision-vite.log 2>&1 &)
curl -sf http://127.0.0.1:8181/healthz >/dev/null || (cd infra && docker compose --env-file "$ROOT/.env" --profile ocr up -d citevision-ocr)
timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null || docker restart citevision-v2-frigate
for i in $(seq 1 30); do timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null && break; sleep 2; done

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "########## COUNTING AUDIT (skip 1hit — already PASS) $(date -Is) ##########"
export SKIP_1HIT=1
export VALIDATE_MODE=audit
bash scripts/validate_rule.sh counting
echo EC_count=$?
unset SKIP_1HIT
export VALIDATE_MODE=wait

echo "########## RED_LIGHT $(date -Is) ##########"
# Ensure OCR + streams + spatial for feux
bash scripts/ensure-demo-streams.sh || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams; echo
# Enable red rule so Frigate record aggregate stays on during rebuild path
# (1hit will toggle; here we pre-warm)
export RULE_DURATION_SEC=480
export SKIP_FRIGATE_REBUILD=1
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
