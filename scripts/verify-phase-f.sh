#!/usr/bin/env bash
# Phase F — lot complet (vitesse arêtes + incidents vidéo)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAIL=0
run() {
  echo ""
  echo ">>> $1"
  if bash "$2"; then echo "[PASS] $1"; else echo "[FAIL] $1"; FAIL=$((FAIL + 1)); fi
}
echo "╔══════════════════════════════════════════════════╗"
echo "║  Phase F — Vitesse arêtes + IA incidents vidéo  ║"
echo "╚══════════════════════════════════════════════════╝"
run "Speed edge calibration" "$SCRIPT_DIR/verify-speed-edge-calibration.sh"
run "Video incidents" "$SCRIPT_DIR/verify-video-incidents.sh"
echo ""
if [[ "$FAIL" -eq 0 ]]; then
  echo "=== Phase F OK ==="
  exit 0
fi
echo "=== Phase F FAILED ($FAIL) ==="
exit 1
