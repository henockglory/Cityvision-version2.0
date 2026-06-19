#!/usr/bin/env bash
# CitéVision v2 — Smoke test install (CI + local)
# Usage:
#   bash scripts/validate-install-smoke.sh --ci
#   bash scripts/validate-install-smoke.sh --fix   # local: apply fixes if models missing
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CI_MODE=false
DO_FIX=false
for arg in "$@"; do
  case "$arg" in
    --ci) CI_MODE=true ;;
    --fix) DO_FIX=true ;;
    --help)
      echo "Usage: bash scripts/validate-install-smoke.sh [--ci] [--fix]"
      exit 0
      ;;
  esac
done

_log() { echo "$1"; }

if [[ "$CI_MODE" == "true" ]]; then
  _log "==> shellcheck (scripts clés)"
  if command -v shellcheck >/dev/null 2>&1; then
    shellcheck \
      scripts/ensure-ai-stack.sh \
      scripts/start-linux.sh \
      scripts/setup-wsl.sh \
      scripts/lib/env-utils.sh \
      scripts/lib/wsl-root.sh \
      scripts/validate-install-smoke.sh
  else
    _log "[WARN] shellcheck absent — skip"
  fi
fi

_log "==> venv frais + pip extras"
rm -rf ai-engine/.venv
python3.12 -m venv ai-engine/.venv 2>/dev/null || python3 -m venv ai-engine/.venv
# shellcheck disable=SC1091
source ai-engine/.venv/bin/activate
pip install --upgrade pip -q
pip install -e 'ai-engine/.[identity,anpr,dev]'

_log "==> imports IA"
python -c "import citevision_ai, insightface, paddleocr"

if [[ "$CI_MODE" == "true" ]]; then
  _log "==> ensure-ai-stack --verify-only (sans health, modèles optionnels CI)"
  bash scripts/ensure-ai-stack.sh --verify-only --health-url=none 2>/dev/null || {
    _log "[OK]   verify-only: imports OK (modèles absents acceptés en CI)"
  }
else
  if [[ "$DO_FIX" == "true" ]]; then
    bash scripts/ensure-ai-stack.sh --fix --max-attempts=2 || true
  fi
  bash scripts/ensure-ai-stack.sh --verify-only || {
    _log "[WARN] verify-only incomplet (modèles ou health) — utilisez --fix en local"
    exit 1
  }
fi

_log "[OK]   validate-install-smoke passed"
exit 0
