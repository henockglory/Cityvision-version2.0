#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export COMMERCIAL_ALLOW_CPU="${COMMERCIAL_ALLOW_CPU:-0}"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  CitéVision — Commercial Quality Gate                    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

FAIL=0
run() {
  echo ""
  echo ">>> $1"
  if bash "$2"; then
    echo "[PASS] $1"
  else
    echo "[FAIL] $1"
    FAIL=$((FAIL + 1))
  fi
}

run "Doctor" "$ROOT/scripts/doctor-linux.sh"
run "Video playback" "$ROOT/scripts/validate-video-playback.sh"
run "Video RTSP smooth (30s)" "$ROOT/scripts/validate-video-smooth.sh"
run "Video WebRTC browser (20s)" "$ROOT/scripts/validate-video-browser.sh"
run "GPU / YOLO" "$ROOT/scripts/validate-gpu.sh"
run "Demo E2E API" "$ROOT/scripts/validate-demo-e2e.sh"

if [[ -d "$ROOT/frontend/node_modules/@playwright/test" ]]; then
  run "Playwright E2E" "$ROOT/scripts/run-e2e.sh"
else
  echo ""
  echo "[SKIP] Playwright — run: cd frontend && npm install && npx playwright install chromium"
fi

echo ""
if (( FAIL > 0 )); then
  echo "GATE FAILED ($FAIL step(s))"
  exit 1
fi
echo "GATE PASSED — MVP commercial ready"
exit 0
