#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

# Confirm go2rtc mount has videos
docker exec citevision-v2-go2rtc ls /videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/ | head -5 || {
  echo "go2rtc videos missing — recreate"
  cd "$ROOT/infra"
  docker compose --env-file "$ROOT/.env" up -d go2rtc
  sleep 3
  bash "$ROOT/scripts/ensure-demo-streams.sh" || true
}

curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY" || true
echo
sleep 5

export RULE_DURATION_SEC=480
export VALIDATE_MODE=wait
# Allow frigate rebuild so record/snapshots on for speeding cam
unset SKIP_FRIGATE_REBUILD || true

echo "=== validate speeding $(date -Is) ==="
bash scripts/validate_rule.sh speeding
echo EXIT=$?
latest=$(find validation-evidence/speeding -name report.json | sort | tail -1)
python3 -c "import json;d=json.load(open('$latest'));print('result',d.get('result'));
[print(c['id'], c['ok'], str(c.get('detail',''))[:120]) for c in (d.get('checks') or [])]"
ls -la "$(dirname "$latest")/ui.png" 2>/dev/null || echo no_ui
