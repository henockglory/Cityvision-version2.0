#!/usr/bin/env bash
# Sequential E2E: 1 detection per rule, order comptage→ceinture→vitesse→téléphone→feu rouge.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export TARGET_DETECTIONS="${TARGET_DETECTIONS:-1}"
export REPORT_TAG=sequential
export DEMO_ORG_ID="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"

echo "==> 1/5 seed-demo-spatial"
bash "$ROOT/scripts/seed-demo-spatial.sh"

echo "==> 2/5 force spatial reload"
bash "$ROOT/scripts/force-spatial-reload.sh"

echo "==> 2.5/5 ensure rules sync + seed demo rules"
export DEMO_ORG_ID="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
bash "$ROOT/scripts/ensure-rules-sync-env.sh" 2>/dev/null || true
load_dotenv "$ENV_FILE"
bash "$ROOT/scripts/seed-demo-rules.sh"

echo "==> 3/5 restart backend (demo alerts)"
stop_from_pid "$ROOT/logs/backend.pid" 2>/dev/null || true
free_port "${API_PORT:-8081}" 2>/dev/null || true
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$ROOT/logs" "$ENV_FILE"
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${API_PORT:-8081}/health" >/dev/null 2>&1 && break
  sleep 2
done

echo "==> 4/5 restart rules-engine"
stop_from_pid "$ROOT/logs/rules-engine.pid" 2>/dev/null || true
free_port "${RULES_ENGINE_PORT:-8010}" 2>/dev/null || true
start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$ROOT/logs" "$ENV_FILE"
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" >/dev/null 2>&1 && break
  sleep 2
done

echo "==> wait backend MQTT alert subscription"
for _ in $(seq 1 45); do
  if grep -q '"mqtt subscribed".*cv/alerts' "$ROOT/logs/backend.log" 2>/dev/null; then
    last_mqtt="$(grep -i mqtt "$ROOT/logs/backend.log" | tail -1)"
    if echo "$last_mqtt" | grep -q 'mqtt subscribed'; then
      echo "OK mqtt alerts subscribed"
      break
    fi
  fi
  sleep 2
done

echo "==> 5/5 validate sequential (target=${TARGET_DETECTIONS}/rule, max ${RULE_TIMEOUT_SEC}s each)"
export PYTHONUNBUFFERED=1
exec python3 "$ROOT/scripts/validate_demo_five_rules.py"
