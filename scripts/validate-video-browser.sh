#!/usr/bin/env bash
# Valide fluidité WebRTC dans le navigateur (currentTime monotone, pas de recul).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
E2E="$ROOT/tests/e2e"
BASE="${E2E_BASE_URL:-http://localhost:5174}"
SEC="${VIDEO_SMOOTH_SEC:-20}"

echo "==> Validation fluidité navigateur WebRTC (${SEC}s) — $BASE/demo"

bash "$ROOT/scripts/validate-video-playback.sh" || exit 1

if ! curl -sf "$BASE" >/dev/null 2>&1; then
  echo "[FAIL] Frontend inaccessible sur $BASE — lancez: bash scripts/start-linux.sh" >&2
  exit 1
fi

cd "$E2E"
if [[ ! -d node_modules/@playwright/test ]]; then
  npm install --silent
  npx playwright install chromium --with-deps 2>/dev/null || npx playwright install chromium
fi

VIDEO_SMOOTH_SEC="$SEC" E2E_BASE_URL="$BASE" npx playwright test video-smooth.spec.ts --reporter=line
echo "[OK] validate-video-browser passed"
