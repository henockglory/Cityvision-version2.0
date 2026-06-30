#!/usr/bin/env bash
# Phase 0.2 — readonly audit gates (no code changes).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="$ROOT/logs/audit-final"
mkdir -p "$LOGDIR"
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
export PUBLIC_API_BASE="${PUBLIC_API_BASE:-http://localhost:8081/api/v1}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
PY="$ROOT/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN=go

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGDIR/audit-run.log"; }

run_gate() {
  local name="$1"
  shift
  log "==> GATE $name"
  if "$@" > "$LOGDIR/gate-${name}.log" 2>&1; then
    echo "PASS" > "$LOGDIR/gate-${name}.status"
    log "PASS $name"
  else
    echo "FAIL" > "$LOGDIR/gate-${name}.status"
    log "FAIL $name (see gate-${name}.log)"
  fi
}

# CRLF fix allowed in Phase 0 for shell scripts only
"$PY" "$ROOT/scripts/fix-crlf.py" "$ROOT/scripts/"*.sh 2>/dev/null || true

run_gate "ensure-ai-stack" bash "$ROOT/scripts/ensure-ai-stack.sh" --verify-only
run_gate "preflight" "$PY" "$ROOT/scripts/preflight_demo_pipeline.py"
run_gate "seed-spatial" bash "$ROOT/scripts/seed-demo-spatial.sh"
run_gate "spatial-reload" bash "$ROOT/scripts/force-spatial-reload.sh"
run_gate "health-curl" bash -c '
  curl -sf http://127.0.0.1:8081/health >/dev/null &&
  curl -sf http://127.0.0.1:8001/health >/dev/null &&
  curl -sf http://127.0.0.1:8010/health >/dev/null &&
  curl -sf http://127.0.0.1:8025/api/v2/messages?limit=1 >/dev/null &&
  curl -sf http://127.0.0.1:9003/minio/health/live >/dev/null
'
run_gate "coverage-matrix" "$PY" "$ROOT/scripts/generate-rule-coverage-matrix.py"
run_gate "go-backend" bash -c "cd '$ROOT/backend' && $GO_BIN test ./... -count=1"
run_gate "go-rules-engine" bash -c "cd '$ROOT/rules-engine' && $GO_BIN test ./... -count=1"
run_gate "pytest-ai" bash -c "cd '$ROOT/ai-engine' && '$PY' -m pytest tests/ -q --tb=no"
run_gate "spatial-live" "$PY" "$ROOT/scripts/check_ai_spatial_live.py"

log "=== audit gates done ==="
for f in "$LOGDIR"/gate-*.status; do
  [[ -f "$f" ]] && echo "$(basename "$f" .status): $(cat "$f")"
done
