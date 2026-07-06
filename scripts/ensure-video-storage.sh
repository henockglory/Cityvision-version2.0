#!/usr/bin/env bash
# Prépare le stockage vidéo neutre (aucune vidéo démo imposée).
# Les flux démo sont téléversés via l'UI (Demo Center / upload API).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

VIDEOS_DIR="$ROOT/data/videos"
mkdir -p "$VIDEOS_DIR/demo"

ENV_FILE="$(ensure_env_file "$ROOT")"
touch "$ENV_FILE"

_ensure_kv() {
  local key="$1" val="$2"
  if grep -q "^${key}=." "$ENV_FILE" 2>/dev/null; then
    return 0
  fi
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE" 2>/dev/null || true
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
  echo "[OK] ${key}=${val}"
}

_ensure_kv VIDEOS_PATH "$VIDEOS_DIR"
sync_project_root "$ROOT"
_ensure_kv PROJECT_ROOT "$ROOT"
# DEMO_VIDEO_PATH volontairement vide — renseigné uniquement si l'utilisateur téléverse une vidéo démo.
if ! grep -q '^DEMO_VIDEO_PATH=.' "$ENV_FILE" 2>/dev/null; then
  if grep -q '^DEMO_VIDEO_PATH=' "$ENV_FILE" 2>/dev/null; then
    :
  else
    echo "DEMO_VIDEO_PATH=" >> "$ENV_FILE"
  fi
fi

export VIDEOS_PATH="$VIDEOS_DIR"
echo "[OK] Stockage vidéo neutre prêt ($VIDEOS_DIR) — téléversez vos vidéos via l'interface démo"
