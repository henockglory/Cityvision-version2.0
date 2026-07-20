#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
mkdir -p logs
LOG="$ROOT/logs/validate-red-final.log"
exec > >(tee "$LOG") 2>&1
echo "=== START $(date -Is) ==="
grep -n 'allow_demo_fallback' ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py | head -3

curl -sf http://127.0.0.1:8081/health >/dev/null || bash scripts/_restart_backend.sh
curl -sf http://127.0.0.1:8010/health >/dev/null || bash scripts/_start-rules-engine.sh
curl -sf http://127.0.0.1:8181/healthz >/dev/null || true
curl -sf http://127.0.0.1:5174/ >/dev/null || true

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial; echo

# Ensure frigate up after prior 502
for i in $(seq 1 40); do
  timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null && break
  sleep 2
done
echo "frigate=$(curl -sf http://127.0.0.1:5000/api/version || echo down)"

export RULE_DURATION_SEC=420
export VALIDATE_MODE=wait
unset SKIP_FRIGATE_REBUILD

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
