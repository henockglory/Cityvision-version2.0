#!/usr/bin/env bash
# Sync demo video files into VIDEOS_PATH and register go2rtc streams at startup.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/install-progress.sh
source "$ROOT/scripts/lib/install-progress.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
API="${BACKEND_API_URL:-http://localhost:${API_PORT:-8081}}"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
VIDEOS="${VIDEOS_PATH:-$ROOT/data/videos}"
GO2RTC="${GO2RTC_URL:-http://localhost:${GO2RTC_PORT:-1984}}"

log_slow_step \
  "Réparation flux vidéo démo (fichiers + go2rtc)" \
  "Synchronise les MP4 vers VIDEOS_PATH et enregistre les streams WebRTC."

_sync_files_from_db() {
  command -v docker >/dev/null 2>&1 || return 0
  docker ps --format '{{.Names}}' | grep -q citevision-v2-postgres || return 0

  local synced=0 missing=0
  while IFS='|' read -r org_id video_id go2rtc_src local_path; do
    [[ -z "$org_id" || -z "$video_id" ]] && continue
    local dest="$VIDEOS/demo/$org_id/${video_id}_stream.mp4"
    local need_copy=false
    if [[ ! -f "$dest" ]] || [[ "$(stat -c%s "$dest" 2>/dev/null || echo 0)" -lt 4096 ]]; then
      need_copy=true
    fi
    if [[ "$need_copy" == "true" ]]; then
      local src="$local_path"
      if [[ ! -f "$src" ]] || [[ "$(stat -c%s "$src" 2>/dev/null || echo 0)" -lt 4096 ]]; then
        for alt in \
          "$local_path" \
          "${local_path//\/mnt\/c\/Users\/gheno\/citevision/$ROOT}" \
          "${local_path//\/mnt\/c\/Citevision/$ROOT}" \
          "$HOME/citevision-v2/data/videos/demo/$org_id/${video_id}_stream.mp4"; do
          if [[ -f "$alt" ]] && [[ "$(stat -c%s "$alt" 2>/dev/null || echo 0)" -gt 4096 ]]; then
            src="$alt"
            break
          fi
        done
      fi
      if [[ ! -f "$src" ]] || [[ "$(stat -c%s "$src" 2>/dev/null || echo 0)" -lt 4096 ]]; then
        missing=$((missing + 1))
        echo "[WARN] fichier démo introuvable: ${video_id} (attendu sous $dest)"
        continue
      fi
      mkdir -p "$(dirname "$dest")"
      cp -f "$src" "$dest"
      synced=$((synced + 1))
      echo "[OK] synced ${video_id}_stream.mp4 -> $dest"
    fi
    if [[ -n "$go2rtc_src" ]] && [[ -f "$dest" ]]; then
      local rel="demo/$org_id/${video_id}_stream.mp4"
      local gsrc="ffmpeg:/videos/${rel}#video=copy#loop"
      if curl -sf -G -X PUT "${GO2RTC}/api/streams" \
        --data-urlencode "name=${go2rtc_src}" \
        --data-urlencode "src=${gsrc}" >/dev/null 2>&1; then
        echo "[OK] go2rtc registered $go2rtc_src"
      else
        echo "[WARN] go2rtc register failed for $go2rtc_src"
      fi
    fi
  done < <(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -F'|' -c \
    "SELECT org_id::text, id::text, COALESCE(go2rtc_src,''), COALESCE(local_stream_path,'')
     FROM org_demo_videos WHERE status='ready' ORDER BY org_id, name;" 2>/dev/null || true)

  echo "[OK] démo fichiers: synced=$synced missing=$missing"
}

_sync_files_from_db

if curl -sf "${API}/health" >/dev/null 2>&1; then
  RESP="$(curl -sf -X POST "${API}/api/v1/internal/demo/repair-streams" \
    -H "X-Internal-Key: ${KEY}" -H "Content-Type: application/json" 2>/dev/null || true)"
  if [[ -n "$RESP" ]]; then
    echo "$RESP" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(f\"[OK] API repair: orgs={d.get('orgs',0)} synced={d.get('files_synced',0)} \"\
          f\"registered={d.get('streams_registered',0)} missing={d.get('files_missing',0)}\")
except Exception:
    pass
" 2>/dev/null || true
  fi
else
  echo "[WARN] Backend absent — réparation go2rtc via shell uniquement"
fi

if curl -sf "${GO2RTC}/api/streams" >/dev/null 2>&1; then
  COUNT="$(curl -sf "${GO2RTC}/api/streams" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)"
  echo "[OK] go2rtc streams enregistrés: $COUNT"
fi
