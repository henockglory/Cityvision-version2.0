#!/usr/bin/env bash
# Sync live-preview UI (go2rtc video-only) Windows mirror -> WSL runtime.
# Never overwrites .env secrets; only ensures VITE_FRIGATE_* flags exist.
set -euo pipefail
SRC="${1:-/mnt/c/Users/gheno/citevision}"
DST="${2:-$HOME/citevision-v2}"

mkdir -p \
  "$DST/frontend/src/config" \
  "$DST/frontend/src/components/live" \
  "$DST/frontend/src/components/demo" \
  "$DST/scripts/lib" \
  "$DST/launcher"

rsync -a --no-owner --no-group --no-perms \
  "$SRC/frontend/src/config/streams.ts" \
  "$DST/frontend/src/config/streams.ts"
rsync -a --no-owner --no-group --no-perms \
  "$SRC/frontend/src/components/live/LiveStreamPlayer.tsx" \
  "$DST/frontend/src/components/live/LiveStreamPlayer.tsx"
rsync -a --no-owner --no-group --no-perms \
  "$SRC/frontend/src/components/live/FrigateLivePlayer.tsx" \
  "$DST/frontend/src/components/live/FrigateLivePlayer.tsx"
rsync -a --no-owner --no-group --no-perms \
  "$SRC/frontend/src/components/demo/DemoVideoPanel.tsx" \
  "$DST/frontend/src/components/demo/DemoVideoPanel.tsx"
rsync -a --no-owner --no-group --no-perms \
  "$SRC/scripts/lib/service-heal.sh" \
  "$DST/scripts/lib/service-heal.sh"
rsync -a --no-owner --no-group --no-perms \
  "$SRC/scripts/lib/sync-live-preview-ui.sh" \
  "$DST/scripts/lib/sync-live-preview-ui.sh" 2>/dev/null || true
# Copy Start PS1 as ASCII-only (em-dash/smart-quotes break Windows PowerShell 5.1).
if [[ -f "$SRC/launcher/Start-CiteVision.ps1" ]]; then
  mkdir -p "$DST/launcher"
  if command -v iconv >/dev/null 2>&1; then
    iconv -f UTF-8 -t ASCII//TRANSLIT "$SRC/launcher/Start-CiteVision.ps1" > "$DST/launcher/Start-CiteVision.ps1" \
      || rsync -a --no-owner --no-group --no-perms "$SRC/launcher/Start-CiteVision.ps1" "$DST/launcher/Start-CiteVision.ps1"
  else
    rsync -a --no-owner --no-group --no-perms "$SRC/launcher/Start-CiteVision.ps1" "$DST/launcher/Start-CiteVision.ps1"
  fi
  # Also refresh Windows launch mirror used by user shortcut C:\Citevision
  if [[ -d /mnt/c/Citevision/launcher ]]; then
    cp -f "$DST/launcher/Start-CiteVision.ps1" /mnt/c/Citevision/launcher/Start-CiteVision.ps1 2>/dev/null || true
  fi
fi

# Frontend Vite flags (preview = go2rtc; Frigate backend unchanged).
fe_env="$DST/frontend/.env"
touch "$fe_env"
grep -q '^VITE_FRIGATE_ENABLED=' "$fe_env" || echo 'VITE_FRIGATE_ENABLED=1' >> "$fe_env"
grep -q '^VITE_FRIGATE_LIVE=' "$fe_env" || echo 'VITE_FRIGATE_LIVE=1' >> "$fe_env"
# Drop mistaken "embed full Frigate UI" origin if present — optional direct link only.
# Keep VITE_FRIGATE_ORIGIN if set (admin link); players no longer iframe /live.

chmod +x "$DST/scripts/lib/sync-live-preview-ui.sh" "$DST/scripts/lib/service-heal.sh" 2>/dev/null || true
sed -i 's/\r$//' "$DST/scripts/lib/sync-live-preview-ui.sh" "$DST/scripts/lib/service-heal.sh" 2>/dev/null || true

# Guard: must not iframe Frigate SPA in LiveStreamPlayer.
if grep -q 'FrigateLivePlayer' "$DST/frontend/src/components/live/LiveStreamPlayer.tsx"; then
  echo "[FAIL] LiveStreamPlayer still imports FrigateLivePlayer" >&2
  exit 1
fi
grep -q 'Go2RtcPlayer' "$DST/frontend/src/components/live/LiveStreamPlayer.tsx"
echo "[OK] live-preview UI synced -> $DST"
