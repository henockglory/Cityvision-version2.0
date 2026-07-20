#!/usr/bin/env bash
# Platform preflight — single gate before demo/validation runs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

BACKEND="${BACKEND_API_URL:-http://127.0.0.1:8081}"
FAIL=0

echo "== CitéVision platform preflight =="

curl -sf "$BACKEND/health" >/dev/null || { echo "FAIL: backend /health"; FAIL=1; }
curl -sf "$BACKEND/health/ready" >/dev/null || { echo "FAIL: backend /health/ready"; FAIL=1; }

PH=$(curl -sf "$BACKEND/health/platform" || echo '{"status":"down"}')
STATUS=$(echo "$PH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','down'))" 2>/dev/null || echo down)
echo "platform health: $STATUS"
if [ "$STATUS" = "down" ]; then
  echo "$PH" | python3 -m json.tool 2>/dev/null || echo "$PH"
  FAIL=1
fi

for url in "${AI_ENGINE_URL:-http://127.0.0.1:8001}/health" "${RULES_ENGINE_URL:-http://127.0.0.1:8010}/health"; do
  curl -sf "$url" >/dev/null || { echo "FAIL: $url"; FAIL=1; }
done

if [ "${FRIGATE_ENABLED:-0}" = "1" ] || [ "${FRIGATE_ENABLED:-false}" = "true" ]; then
  curl -sf "${FRIGATE_URL:-http://127.0.0.1:5000}/api/version" >/dev/null || echo "WARN: Frigate API unreachable"
fi

if [ -f scripts/preflight_demo_pipeline.py ]; then
  python3 scripts/preflight_demo_pipeline.py || FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
  echo "PREFLIGHT FAILED"
  exit 1
fi
echo "PREFLIGHT OK"
exit 0
