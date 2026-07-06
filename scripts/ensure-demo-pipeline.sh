#!/usr/bin/env bash
# Ensure rules-engine + AI ingest are up (required for Détections/Alertes demo pipeline).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
AI_PORT="${AI_ENGINE_PORT:-8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"
API_PORT="${API_PORT:-8081}"
INTERNAL_KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
VENV_PY="${ROOT}/ai-engine/.venv/bin/python3"
[[ -x "$VENV_PY" ]] || VENV_PY="$(command -v python3)"

echo "==> ensure-demo-pipeline (rules-engine + AI + resync)"

if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
  echo "[FAIL] Backend not running on :${API_PORT} — start backend first" >&2
  exit 1
fi

bash "$ROOT/scripts/ensure-rules-sync-env.sh" --resolve-org 2>/dev/null || true
load_dotenv "$ENV_FILE"

if ! curl -sf "http://127.0.0.1:${RULES_PORT}/health" >/dev/null 2>&1; then
  echo "[INFO] Starting rules-engine :${RULES_PORT}"
  bash "$ROOT/scripts/_start-rules-engine.sh"
else
  ACTIVE_PRE="$("$VENV_PY" -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:${RULES_PORT}/health')).get('active_rules',0))" 2>/dev/null || echo 0)"
  if [[ "${ACTIVE_PRE}" == "0" ]]; then
    echo "[WARN] rules-engine up but active_rules=0 — restarting for rule sync"
    bash "$ROOT/scripts/_start-rules-engine.sh"
  fi
fi
if ! wait_http_ok "http://127.0.0.1:${RULES_PORT}/health" 60; then
  echo "[FAIL] rules-engine not healthy" >&2
  exit 1
fi
echo "[OK] rules-engine :${RULES_PORT}"

if ! curl -sf "http://127.0.0.1:${AI_PORT}/health" >/dev/null 2>&1; then
  echo "[INFO] Starting AI engine :${AI_PORT}"
  setup_cuda_library_path "$VENV_PY"
  stop_from_pid "$LOGDIR/ai-engine.pid" 2>/dev/null || true
  start_bg ai-engine "$ROOT" "bash scripts/run-ai-engine.sh" "$LOGDIR" "$ENV_FILE"
fi
if ! wait_http_ok "http://127.0.0.1:${AI_PORT}/health" 120; then
  echo "[FAIL] AI engine not healthy" >&2
  exit 1
fi
echo "[OK] AI engine :${AI_PORT}"

curl -sf -X POST "http://127.0.0.1:${API_PORT}/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: ${INTERNAL_KEY}" >/dev/null || true
echo "[INFO] resync-spatial sent — waiting for camera ingest (up to 90s)"

running_count() {
  curl -sf "http://127.0.0.1:${AI_PORT}/cameras" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for x in (d.get('cameras') or []) if x.get('running')))" 2>/dev/null \
    || echo 0
}

for _ in $(seq 1 18); do
  rc="$(running_count)"
  if [[ "$rc" -ge 1 ]]; then
    echo "[OK] AI camera ingest running (${rc})"
    break
  fi
  sleep 5
done
if [[ "$(running_count)" -lt 1 ]]; then
  echo "[WARN] no running ingest — resync + retry"
  curl -sf -X POST "http://127.0.0.1:${API_PORT}/api/v1/internal/ingest/resync-spatial" \
    -H "X-Internal-Key: ${INTERNAL_KEY}" >/dev/null || true
  sleep 20
fi

ACTIVE="$("$VENV_PY" -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:${RULES_PORT}/health')).get('active_rules',0))" 2>/dev/null || echo 0)"
echo "[OK] active_rules=${ACTIVE}"

if ! bash "$ROOT/scripts/verify-ai-ingest.sh"; then
  echo "[WARN] ingest stalled — restarting AI once"
  bash "$ROOT/scripts/restart-ai-engine.sh" || true
  curl -sf -X POST "http://127.0.0.1:${API_PORT}/api/v1/internal/ingest/resync-spatial" \
    -H "X-Internal-Key: ${INTERNAL_KEY}" >/dev/null || true
  sleep 15
  bash "$ROOT/scripts/verify-ai-ingest.sh"
fi

if [[ "${WATCH_AI_INGEST:-1}" != "0" ]]; then
  wp="$LOGDIR/watch-ai-ingest.pid"
  alive=0
  if [[ -f "$wp" ]]; then
    wpid="$(cat "$wp" 2>/dev/null || echo 0)"
    kill -0 "$wpid" 2>/dev/null && alive=1
  fi
  if [[ "$alive" -eq 0 ]]; then
    stop_from_pid "$wp" 2>/dev/null || true
    start_bg watch-ai-ingest "$ROOT" "bash scripts/watch-ai-ingest.sh" "$LOGDIR" "$ENV_FILE"
    echo "[OK] AI ingest watchdog started"
  fi
fi
echo "[OK] demo pipeline ready"
