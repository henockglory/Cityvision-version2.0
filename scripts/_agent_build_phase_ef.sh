#!/usr/bin/env bash
set -euo pipefail
SRC="/mnt/c/Users/gheno/citevision"
RUNTIME="${HOME}/citevision-v2"
export PATH="${PATH}:/usr/local/go/bin:/home/gheno/go/bin"

sync_file() {
  local f="$1"
  mkdir -p "$(dirname "${RUNTIME}/${f}")"
  sed 's/\r$//' < "${SRC}/${f}" > "${RUNTIME}/${f}"
}

echo "== Phase E+F sync =="
for f in \
  scripts/validate-install-gate.sh \
  scripts/verify-speed-edge-calibration.sh \
  scripts/verify-video-incidents.sh \
  scripts/verify-phase-f.sh \
  scripts/install-headless.sh \
  ai-engine/tests/test_video_quality.py \
  frontend/src/pages/ZoneEditor.tsx; do
  sync_file "$f"
done
chmod +x "${RUNTIME}/scripts/validate-install-gate.sh" \
  "${RUNTIME}/scripts/verify-speed-edge-calibration.sh" \
  "${RUNTIME}/scripts/verify-video-incidents.sh" \
  "${RUNTIME}/scripts/verify-phase-f.sh"

echo "== Phase E gate =="
bash "${RUNTIME}/scripts/validate-install-gate.sh" | tail -8

echo "== Phase F =="
bash "${RUNTIME}/scripts/verify-phase-f.sh" 2>&1 | tail -15
