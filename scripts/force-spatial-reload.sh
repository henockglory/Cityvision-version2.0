#!/usr/bin/env bash
# Force spatial config re-push: DB seed → orchestrator invalidate → AI verify.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

API_PORT="${API_PORT:-8081}"
AI_PORT="${AI_ENGINE_PORT:-8001}"
ORG="${DEFAULT_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
FEUX="${DEMO_FEUX_CAMERA_ID:-726ff8a1-8442-4bdb-96ad-ec40a2fbb424}"
LIGNE="${DEMO_LIGNE_CAMERA_ID:-01ee632c-271c-4e66-ba98-3d1d7e430c09}"
INTERNAL_KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
PY="${ROOT}/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

echo "==> 1/4 seed-demo-spatial (idempotent)"
bash "$ROOT/scripts/seed-demo-spatial.sh"

echo "==> 2/4 resync-spatial (immediate orchestrator sync)"
curl -sf -X POST "http://127.0.0.1:${API_PORT}/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: ${INTERNAL_KEY}" | "$PY" -m json.tool || {
  echo "[WARN] resync-spatial failed — restarting backend ingest"
  bash "$ROOT/scripts/restart-ai-ingest.sh"
}

echo "==> 3/4 wait orchestrator hot-reload (~12s)"
sleep 12

echo "==> orchestrator spatial-config (Feux)"
curl -sf "http://127.0.0.1:${API_PORT}/api/v1/internal/ingest/orgs/${ORG}/cameras/${FEUX}/spatial-config" \
  -H "X-Internal-Key: ${INTERNAL_KEY}" | "$PY" -m json.tool | head -25 || true

echo "==> AI live spatial (Feux)"
curl -sf "http://127.0.0.1:${AI_PORT}/cameras/${FEUX}/spatial" | "$PY" -m json.tool || echo "[WARN] AI spatial endpoint unavailable"

echo "==> 4/4 push spatial from API (feux + ligne) + reset state machines"
"$PY" "$ROOT/scripts/push_ai_spatial_from_api.py"
sleep 8
curl -sf "http://127.0.0.1:${AI_PORT}/cameras/${FEUX}/spatial" | "$PY" -m json.tool || true
curl -sf "http://127.0.0.1:${AI_PORT}/cameras/${LIGNE}/spatial" | "$PY" -m json.tool || true

echo "==> MQTT monitor (60s)"
"$PY" "$ROOT/scripts/mqtt_monitor_events.py" 60 || true

echo "==> done — run: python3 scripts/check_ai_spatial_live.py"
