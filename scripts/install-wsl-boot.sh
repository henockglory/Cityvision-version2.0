#!/usr/bin/env bash
# Sprint 3 — install WSL boot hook so dockerd + infra restart after wsl --shutdown.
# Requires sudo once. Does NOT enable Docker Desktop.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BOOT_SCRIPT="$ROOT/scripts/wsl-boot-stack.sh"
chmod +x "$BOOT_SCRIPT" "$ROOT/scripts/_start_dockerd_wsl.sh" || true

CONF=/etc/wsl.conf
MARKER_BEGIN="# BEGIN citevision-boot"
MARKER_END="# END citevision-boot"

echo "Installing WSL boot hook → $BOOT_SCRIPT"

TMP="$(mktemp)"
if [[ -f "$CONF" ]]; then
  # Strip previous citevision block
  awk -v b="$MARKER_BEGIN" -v e="$MARKER_END" '
    $0==b {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}
  ' "$CONF" >"$TMP"
else
  : >"$TMP"
fi

# Ensure [boot] section with our command (append block)
{
  cat "$TMP"
  echo ""
  echo "$MARKER_BEGIN"
  echo "[boot]"
  echo "command = $BOOT_SCRIPT"
  echo "$MARKER_END"
} | sudo tee "$CONF" >/dev/null

rm -f "$TMP"
echo "Wrote $CONF"
echo "Apply with: wsl.exe --shutdown   then reopen Ubuntu"
echo "Log: /tmp/citevision-wsl-boot.log"
cat "$CONF"
