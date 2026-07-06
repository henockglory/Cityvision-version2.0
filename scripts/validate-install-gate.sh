#!/usr/bin/env bash
# Phase E — Gate installateur machine vierge (lecture seule, sans réinstall)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="${PATH}:/usr/local/go/bin"
export ROOT
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

FAIL=0
REPORT="$ROOT/logs/install-gate-report.json"
mkdir -p "$ROOT/logs"
RESULTS_FILE="$(mktemp)"

pass() { echo "PASS|$1" >> "$RESULTS_FILE"; echo "[PASS] $1"; }
fail() { echo "FAIL|$1" >> "$RESULTS_FILE"; echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }
warn() { echo "WARN|$1" >> "$RESULTS_FILE"; echo "[WARN] $1"; }

echo "=== Phase E — validate-install-gate ==="

ENV_FILE="$(ensure_env_file "$ROOT" 2>/dev/null || echo "$ROOT/.env")"
load_dotenv "$ENV_FILE"
BACKEND_PORT="${API_PORT:-8081}"
AI_PORT="${AI_ENGINE_PORT:-8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"
FRONTEND_PORT="5174"

[[ -f "$ROOT/.env" ]] && pass ".env présent" || fail ".env absent"
[[ -f "$ROOT/shared/ai-stack-registry.json" ]] && pass "ai-stack-registry.json" || fail "ai-stack-registry.json"
[[ -f "$ROOT/installer/linux/bootstrap.sh" ]] && pass "installer/linux/bootstrap.sh" || fail "bootstrap.sh"
[[ -f "$ROOT/scripts/install-headless.sh" ]] && pass "install-headless.sh" || fail "install-headless.sh"

command -v docker >/dev/null && pass "docker CLI" || fail "docker CLI"
docker info >/dev/null 2>&1 && pass "docker daemon" || fail "docker daemon"

if curl -sf "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
  pass "backend :$BACKEND_PORT"
else
  fail "backend :$BACKEND_PORT"
fi

if curl -sf "http://127.0.0.1:$AI_PORT/health" >/dev/null 2>&1; then
  pass "ai-engine :$AI_PORT"
  VENV_PY="$ROOT/ai-engine/.venv/bin/python3"
  GPU_FLAG=()
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    GPU_FLAG=(--require-gpu)
  fi
  if [[ -x "$VENV_PY" ]] && "$VENV_PY" "$ROOT/ai-engine/scripts/check_ai_health.py" \
      --url "http://127.0.0.1:$AI_PORT/health" "${GPU_FLAG[@]}" 2>/dev/null; then
    pass "ai registry health keys"
  else
    fail "ai registry health keys"
  fi
else
  fail "ai-engine :$AI_PORT"
fi

if curl -sf "http://127.0.0.1:$RULES_PORT/health" >/dev/null 2>&1; then
  pass "rules-engine :$RULES_PORT"
else
  fail "rules-engine :$RULES_PORT"
fi

if curl -sf "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
  pass "frontend :$FRONTEND_PORT"
else
  warn "frontend :$FRONTEND_PORT"
fi

SETUP_INIT="unknown"
if STATUS_JSON=$(curl -sf "http://127.0.0.1:$BACKEND_PORT/api/v1/setup/status" 2>/dev/null); then
  SETUP_INIT=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('initialized', False))")
  pass "setup/status API"
else
  fail "setup/status API"
fi

python3 <<PY > "$REPORT"
import json
from datetime import datetime, timezone
from pathlib import Path

results = []
for line in Path("$RESULTS_FILE").read_text(encoding="utf-8").splitlines():
    if "|" not in line:
        continue
    status, name = line.split("|", 1)
    results.append({"check": name, "status": status})

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "phase": "E",
    "status": "OK" if $FAIL == 0 else "FAIL",
    "fail_count": $FAIL,
    "backend_port": $BACKEND_PORT,
    "ai_port": $AI_PORT,
    "setup_initialized": "$SETUP_INIT",
    "checks": results,
}
print(json.dumps(report, indent=2, ensure_ascii=False))
PY

rm -f "$RESULTS_FILE"

echo ""
echo "Rapport: $REPORT"
if [[ "$FAIL" -eq 0 ]]; then
  echo "=== validate-install-gate OK ==="
  exit 0
fi
echo "=== validate-install-gate FAILED ($FAIL) ==="
exit 1
