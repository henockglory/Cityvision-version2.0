#!/usr/bin/env bash
# Feu rouge: monitor until red_light_violation OR green+amber+red (max 10 min).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export FEUX_MONITOR_MAX_SEC="${FEUX_MONITOR_MAX_SEC:-600}"
export FEUX_REPORT_JSON="$ROOT/logs/feux-monitor-report.json"
PY="$ROOT/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

echo "==> seed-demo-spatial + force reload (Feux cold start)"
bash "$ROOT/scripts/seed-demo-spatial.sh"
bash "$ROOT/scripts/force-spatial-reload.sh"

echo "==> monitor until violation OR 3 colors (max ${FEUX_MONITOR_MAX_SEC}s)"
export PYTHONUNBUFFERED=1
"$PY" "$ROOT/scripts/monitor_feux_until_success.py"

echo "==> synthetic feu alert chain (no video dependency)"
"$PY" "$ROOT/scripts/test_feux_alert_chain.py"
