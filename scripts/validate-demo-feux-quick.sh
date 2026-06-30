#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export TARGET_DETECTIONS="${TARGET_DETECTIONS:-2}"
export VALIDATE_ONLY="Démo · Feu rouge"

echo "==> push spatial (feux) — no full stack restart"
"$ROOT/ai-engine/.venv/bin/python3" "$ROOT/scripts/push_ai_spatial_from_api.py" || true
sleep 10

echo "==> restart rules-engine only"
stop_from_pid "$ROOT/logs/rules-engine.pid" 2>/dev/null || true
free_port "${RULES_ENGINE_PORT:-8010}" 2>/dev/null || true
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$ROOT/logs" "$ENV_FILE"
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" >/dev/null 2>&1 && break
  sleep 2
done

export PYTHONUNBUFFERED=1
exec python3 "$ROOT/scripts/validate_demo_five_rules.py"
