#!/usr/bin/env bash
# Re-validate feu rouge only after demo alert fix.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export TARGET_DETECTIONS="${TARGET_DETECTIONS:-2}"
export VALIDATE_ONLY="Démo · Feu rouge"

echo "==> seed-demo-spatial + force reload"
bash "$ROOT/scripts/seed-demo-spatial.sh"
bash "$ROOT/scripts/force-spatial-reload.sh"

echo "==> ensure rules sync"
bash "$ROOT/scripts/ensure-rules-sync-env.sh" 2>/dev/null || true
load_dotenv "$ENV_FILE"
bash "$ROOT/scripts/seed-demo-rules.sh" 2>/dev/null || true

echo "==> restart backend (alerts demo fix)"
stop_from_pid "$ROOT/logs/backend.pid" 2>/dev/null || true
free_port "${API_PORT:-8081}" 2>/dev/null || true
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$ROOT/logs" "$ENV_FILE"
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${API_PORT:-8081}/health" >/dev/null 2>&1 && break
  sleep 2
done

echo "==> restart rules-engine (demo alert policy)"
stop_from_pid "$ROOT/logs/rules-engine.pid" 2>/dev/null || true
free_port "${RULES_ENGINE_PORT:-8010}" 2>/dev/null || true
start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$ROOT/logs" "$ENV_FILE"
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" >/dev/null 2>&1 && break
  sleep 2
done
for _ in $(seq 1 45); do
  last_mqtt="$(grep -i mqtt "$ROOT/logs/backend.log" 2>/dev/null | tail -1 || true)"
  if echo "$last_mqtt" | grep -q 'mqtt subscribed'; then break; fi
  sleep 2
done

echo "==> restart ai-engine"
bash "$ROOT/scripts/restart-ai-ingest.sh" >"$ROOT/logs/restart-ai-feux.log" 2>&1 || true
sleep 8

export PYTHONUNBUFFERED=1
exec python3 "$ROOT/scripts/validate_demo_five_rules.py"
