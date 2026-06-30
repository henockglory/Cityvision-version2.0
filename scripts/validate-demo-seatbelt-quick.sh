#!/usr/bin/env bash
# Quick seatbelt-only validation: 1 detection, max 3 min.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-180}"
export TARGET_DETECTIONS=1
export REPORT_TAG=seatbelt-quick
export VALIDATE_ONLY="Démo · Non-port ceinture"

echo "==> restart rules-engine (alert-first fix)"
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
