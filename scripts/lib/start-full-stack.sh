#!/usr/bin/env bash
# Unified full-stack start — used by start-linux.sh, launcher/Start-CiteVision.ps1,
# and installer /api/launch. Exit 0 only when service gate + health_check_all pass.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PATH="${PATH:-}:/usr/local/go/bin:/home/gheno/go/bin"

# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/cuda-utils.sh
source "$ROOT/scripts/lib/cuda-utils.sh"

if [[ "$ROOT" == /mnt/c/* ]] || [[ "$ROOT" == /mnt/d/* ]]; then
  echo "[FAIL] Refuse ROOT under /mnt/* (got $ROOT). Use native WSL tree e.g. \$HOME/citevision-v2" >&2
  exit 1
fi

LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR" "$ROOT/backend/bin" "$ROOT/data/videos"
export CITEVISION_LOGDIR="$LOGDIR"

echo "=== CitéVision START FULL STACK $(date -Is) ==="
echo "ROOT=$ROOT"

ENV_FILE="$(ensure_env_file "$ROOT")"
sync_project_root "$ROOT"
ensure_demo_runtime_env "$ROOT" "$ENV_FILE"
load_dotenv "$ENV_FILE"

export RULE_CATALOG_PATH="${RULE_CATALOG_PATH:-$ROOT/shared/rule-catalog}"
export SHARED_PATH="${SHARED_PATH:-$ROOT/shared}"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
BACKEND_PORT="${API_PORT:-8081}"
AI_PORT="${AI_ENGINE_PORT:-8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"

# --- dockerd ---
echo "=== [1/10] dockerd ==="
ensure_docker_ready 120 install || exit 1
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[OK] NVIDIA GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)"
else
  echo "[WARN] nvidia-smi absent — AI may fall back to CPU"
fi

# --- infra + Frigate + OCR ---
echo "=== [2/10] docker compose (frigate + ocr profiles) ==="
bash "$ROOT/scripts/ensure-video-storage.sh" 2>/dev/null || true
cd "$ROOT/infra"
docker compose --env-file "$ENV_FILE" --profile frigate --profile ocr up -d \
  postgres redis mosquitto minio go2rtc mailhog citevision-ocr frigate 2>&1 | tail -25 || true
# Named services may still need profile; retry profiles if frigate missing
if ! docker ps --format '{{.Names}}' | grep -q citevision-v2-frigate; then
  docker compose --env-file "$ENV_FILE" --profile frigate up -d frigate 2>&1 | tail -10 || true
fi
if ! docker ps --format '{{.Names}}' | grep -q citevision-v2-ocr; then
  docker compose --env-file "$ENV_FILE" --profile ocr up -d citevision-ocr 2>&1 | tail -10 || true
fi
cd "$ROOT"
sleep 5

for i in $(seq 1 45); do
  docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 && break
  sleep 2
done
docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 \
  || { echo "[FAIL] postgres"; exit 1; }

if ! wait_http_ok "http://127.0.0.1:1984/api" 60; then
  echo "[WARN] go2rtc slow — restart"
  docker restart citevision-v2-go2rtc >/dev/null 2>&1 || true
  sleep 3
  wait_http_ok "http://127.0.0.1:1984/api" 60 || { echo "[FAIL] go2rtc"; exit 1; }
fi
echo "[OK] postgres + go2rtc"

if ! docker exec citevision-v2-go2rtc ls /videos >/dev/null 2>&1; then
  echo "[WARN] /videos missing in go2rtc — recreate"
  docker rm -f citevision-v2-go2rtc 2>/dev/null || true
  (cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" up -d go2rtc)
  sleep 3
fi

# --- AI stack (venv + models) ---
echo "=== [3/10] AI stack (ensure-ai-stack) ==="
if ! bash "$ROOT/scripts/ensure-ai-stack.sh" --fix --max-attempts=5; then
  echo "[FAIL] AI stack incomplete" >&2
  exit 1
fi
if ! ensure_frontend_deps "$ROOT"; then
  echo "[FAIL] Frontend deps — run setup-wsl.sh" >&2
  exit 1
fi

# --- free ports & start backend / rules / AI ---
echo "=== [4/10] backend + rules + AI ==="
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go || true)"
[[ -n "$GO_BIN" ]] || { echo "[FAIL] go not found"; exit 1; }

free_port 8081 8001 8010 5174 5175 5176 5177 2>/dev/null || true
sleep 1
bash "$ROOT/scripts/ensure-rules-sync-env.sh" --static-only 2>/dev/null || true
load_dotenv "$ENV_FILE"

# Prefer prebuilt binary when present (faster / matches _restart_backend)
if [[ -x "$ROOT/backend/bin/citevision-api" ]]; then
  python3 "$ROOT/scripts/_restart_backend.py" || true
else
  start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$LOGDIR" "$ENV_FILE"
fi
if ! wait_http_ok "http://127.0.0.1:${BACKEND_PORT}/health" 120; then
  echo "[FAIL] backend health" >&2
  tail -40 "$LOGDIR/backend.log" 2>/dev/null || true
  exit 1
fi
echo "[OK] backend :${BACKEND_PORT}"

bash "$ROOT/scripts/ensure-demo-streams.sh" || echo "[WARN] ensure-demo-streams"
bash "$ROOT/scripts/ensure-rules-sync-env.sh" --resolve-org 2>/dev/null || true
load_dotenv "$ENV_FILE"

bash "$ROOT/scripts/_start-rules-engine.sh" 2>&1 | tail -15 || \
  start_bg rules-engine "$ROOT/rules-engine" "$GO_BIN run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:${RULES_PORT}/health" 60 || { echo "[FAIL] rules-engine"; exit 1; }
echo "[OK] rules-engine :${RULES_PORT}"

VENV_PY="${ROOT}/ai-engine/.venv/bin/python3"
setup_cuda_library_path "$VENV_PY" 2>/dev/null || true
bash "$ROOT/scripts/_copy_working_cudnn.sh" 2>/dev/null || true
if [[ -f "$ROOT/scripts/_restart_ai.py" ]]; then
  python3 "$ROOT/scripts/_restart_ai.py" || true
else
  start_bg ai-engine "$ROOT" "bash scripts/run-ai-engine.sh" "$LOGDIR" "$ENV_FILE"
fi
if ! wait_http_ok "http://127.0.0.1:${AI_PORT}/health" 180; then
  echo "[FAIL] AI health" >&2
  exit 1
fi
bash "$ROOT/scripts/ensure-ai-stack.sh" --fix --restart-ai \
  --health-url="http://127.0.0.1:${AI_PORT}/health" --max-attempts=3 || true
echo "[OK] AI :${AI_PORT}"

# --- Frigate heal + demo pipeline ---
echo "=== [5/10] repair-streams + Frigate ==="
for _ in 1 2 3; do
  curl -sf -X POST "http://127.0.0.1:${BACKEND_PORT}/api/v1/internal/demo/repair-streams" \
    -H "X-Internal-Key: $KEY" && break
  sleep 3
done || true
curl -sf -X POST "http://127.0.0.1:${BACKEND_PORT}/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: $KEY" || true

if ! wait_http_ok "http://127.0.0.1:5000/api/version" 90; then
  echo "[WARN] Frigate down — recreate"
  (cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" --profile frigate up -d frigate)
  wait_http_ok "http://127.0.0.1:5000/api/version" 120 || { echo "[FAIL] Frigate"; exit 1; }
fi
export SKIP_FRIGATE_EVENTS_WAIT=1
bash "$ROOT/scripts/_heal_frigate_now.sh" 2>&1 | tail -20 || true
echo "[OK] Frigate $(curl -sf http://127.0.0.1:5000/api/version 2>/dev/null || echo up)"

# Ingest / demo pipeline is best-effort at launch — NOT a hard gate.
# Cameras may be offline; rules may be disabled; frames advance later via watchdog.
echo "=== [6/10] demo pipeline (best-effort, no ingest gate) ==="
export SKIP_AI_INGEST_VERIFY=1
bash "$ROOT/scripts/ensure-demo-pipeline.sh" 2>&1 | tail -20 || true
curl -sf -X POST "http://127.0.0.1:${BACKEND_PORT}/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: $KEY" >/dev/null || true
n=$(curl -sf "http://127.0.0.1:${AI_PORT}/cameras" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(sum(1 for x in (d.get('cameras') or []) if x.get('running')))" 2>/dev/null || echo 0)
echo "[INFO] AI cameras running=${n:-0} (ingest not required for launch OK)"

# --- frontend ---
echo "=== [7/10] frontend :5174 ==="
bash "$ROOT/scripts/ensure-frontend.sh" 2>&1 | tail -20 || \
  start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:5174/" 90 || { echo "[FAIL] frontend"; exit 1; }
echo "[OK] frontend"

# --- watchdogs ---
if [[ "${WATCH_BACKEND:-1}" != "0" ]]; then
  stop_from_pid "$LOGDIR/watch-backend.pid" 2>/dev/null || true
  start_bg watch-backend "$ROOT" "bash scripts/watch-backend.sh" "$LOGDIR" "$ENV_FILE"
fi
if [[ "${WATCH_AI_INGEST:-1}" != "0" ]]; then
  stop_from_pid "$LOGDIR/watch-ai-ingest.pid" 2>/dev/null || true
  start_bg watch-ai-ingest "$ROOT" "bash scripts/watch-ai-ingest.sh" "$LOGDIR" "$ENV_FILE"
fi

# --- service gate (hard) ---
echo "=== [8/10] service URL gate ==="
python3 - <<'PY'
import urllib.request, sys
checks = [
  ("API", "http://127.0.0.1:8081/health"),
  ("AI", "http://127.0.0.1:8001/health"),
  ("RULES", "http://127.0.0.1:8010/health"),
  ("UI", "http://127.0.0.1:5174/"),
  ("FRIGATE", "http://127.0.0.1:5000/api/version"),
  ("GO2RTC", "http://127.0.0.1:1984/api"),
  ("MAILHOG", "http://127.0.0.1:8025/"),
  ("OCR", "http://127.0.0.1:8181/healthz"),
]
fail = 0
for name, url in checks:
  try:
    urllib.request.urlopen(url, timeout=5).read(64)
    print(f"[GATE OK] {name}")
  except Exception as e:
    print(f"[GATE FAIL] {name}: {e}")
    fail = 1
sys.exit(fail)
PY

# --- health_check_all (WARN disk OK; FAIL services abort) ---
echo "=== [9/10] health_check_all ==="
set +e
bash "$ROOT/scripts/health_check_all.sh"
HC=$?
set -e
if [[ "$HC" -ne 0 ]]; then
  echo "[FAIL] health_check_all exit=$HC — launch aborted (service FAIL; disk WARN alone is OK)" >&2
  exit 1
fi
echo "[OK] health_check_all GREEN/YELLOW (exit 0)"

echo "=== [10/10] READY ==="
echo "  UI        http://127.0.0.1:5174"
echo "  API       http://127.0.0.1:${BACKEND_PORT}"
echo "  AI        http://127.0.0.1:${AI_PORT}"
echo "  Rules     http://127.0.0.1:${RULES_PORT}"
echo "  Frigate   http://127.0.0.1:5000"
echo "  OCR       http://127.0.0.1:8181"
echo "  Mailhog   http://127.0.0.1:8025"
echo "  go2rtc    http://127.0.0.1:1984"
echo "Stop: bash scripts/stop-linux.sh  |  launcher/Stop-CiteVision.ps1"
exit 0
