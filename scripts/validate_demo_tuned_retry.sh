#!/usr/bin/env bash
# Re-run E2E for feu rouge, vitesse, téléphone — 10 min max each, stop at 2 hits.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export TARGET_DETECTIONS="${TARGET_DETECTIONS:-2}"
export PYTHONUNBUFFERED=1

echo "==> restart ingest (clean AI + orchestrator baseline)"
bash "$ROOT/scripts/restart-ai-ingest.sh" 2>&1 | tail -12

echo "==> spatial tuning (default zones per demo video)"
bash "$ROOT/scripts/force-spatial-reload.sh"

echo "==> restart rules-engine (evidence OR targets + demo partial evidence)"
bash "$ROOT/scripts/_start-rules-engine.sh" 2>&1 | tail -5

echo "==> seed demo rules (disabled — validation enables one at a time)"
DEMO_RULES_ENABLED=0 bash "$ROOT/scripts/seed-demo-rules.sh"

echo "==> tuned retry validation (3 rules)"
PY="${ROOT}/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"
exec "$PY" -u "$ROOT/scripts/validate_demo_tuned_retry.py"
