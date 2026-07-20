#!/usr/bin/env bash
# Sync launch/health alignment files from Windows edit tree to 4 mirrors.
set -euo pipefail
SRC="${1:-/mnt/c/Users/gheno/citevision}"
FILES=(
  scripts/lib/start-full-stack.sh
  scripts/lib/env-utils.sh
  scripts/start-linux.sh
  scripts/setup-wsl.sh
  launcher/Start-CiteVision.ps1
  installer/deps-checker.py
  setup.bat
  setup.sh
  .env.example
  scripts/_sync_health_launch.sh
  scripts/_verify_health_launch.sh
  scripts/_run_start_full_verify.sh
)

sync_one() {
  local DST="$1"
  [[ -d "$DST" ]] || { echo "[SKIP] missing $DST"; return 0; }
  for f in "${FILES[@]}"; do
    mkdir -p "$DST/$(dirname "$f")"
    cp -f "$SRC/$f" "$DST/$f"
    case "$f" in
      *.sh|*.py|*.example) sed -i 's/\r$//' "$DST/$f" ;;
    esac
  done
  chmod +x "$DST/scripts/lib/start-full-stack.sh" "$DST/scripts/start-linux.sh" "$DST/scripts/setup-wsl.sh" 2>/dev/null || true
  echo "[OK] synced -> $DST"
}

sync_one "${HOME}/citevision-v2"
sync_one "/mnt/c/Users/gheno/citevision-v2"
sync_one "/mnt/c/Citevision"
sync_one "/mnt/c/Users/gheno/citevision_optimized"
echo DONE
