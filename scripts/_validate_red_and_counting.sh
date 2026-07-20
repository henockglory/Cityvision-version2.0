#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== heal frigate ==="
docker restart citevision-v2-frigate
for i in $(seq 1 40); do
  if timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
    echo "frigate OK $(curl -sf http://127.0.0.1:5000/api/version)"
    break
  fi
  sleep 2
done

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild -H "X-Internal-Key: $KEY" || true
echo
sleep 5
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY" || true
echo

bash scripts/health_check_all.sh || {
  echo "still not green — continue if only WARN"
}

export RULE_DURATION_SEC=480
export VALIDATE_MODE=wait
export SKIP_FRIGATE_REBUILD=1

echo "########## RED_LIGHT $(date -Is) ##########"
bash scripts/validate_rule.sh red_light
echo EC_red=$?
latest=$(find validation-evidence/red_light -name report.json | sort | tail -1)
python3 -c "import json;d=json.load(open('$latest'));print('red_light', d.get('result'))"
ls -la "$(dirname "$latest")/ui.png" 2>/dev/null || echo no_ui

echo "########## COUNTING $(date -Is) ##########"
bash scripts/validate_rule.sh counting
echo EC_count=$?
latest=$(find validation-evidence/counting -name report.json | sort | tail -1)
if [[ -n "$latest" ]]; then
  python3 -c "import json;d=json.load(open('$latest'));print('counting', d.get('result'))"
  ls -la "$(dirname "$latest")/ui.png" 2>/dev/null || echo no_ui
else
  echo counting NO_ARTEFACT
fi

echo "=== FINAL SCORECARD ==="
for a in speeding red_light phone seatbelt counting; do
  latest=$(find validation-evidence/$a -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "$latest" ]]; then
    python3 -c "import json,os;d=json.load(open('$latest'));print(d.get('result'), '$a', 'ui='+str(os.path.exists('$(dirname "$latest")/ui.png')))"
  else
    echo "NONE $a"
  fi
done
