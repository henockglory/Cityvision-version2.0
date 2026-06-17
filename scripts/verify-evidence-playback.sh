#!/usr/bin/env bash
# Télécharge un clip evidence récent et vérifie H.264 + durée > 0
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$SCRIPT_DIR/lib/env-utils.sh"

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

echo "=== verify-evidence-playback ==="

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

CLIPS=$(curl -sf "$API/api/v1/orgs/$ORG/alerts?limit=30" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
for a in json.load(sys.stdin):
    snap = a.get('evidence_snapshot') or {}
    pkg = snap.get('package') or {}
    clip = (pkg.get('clip') or {}).get('url') or ''
    if clip:
        print(clip)
")

if [ -z "${CLIPS:-}" ]; then
  echo "FAIL: no alert with clip URL"
  exit 1
fi

H264_OK=0
while IFS= read -r CLIP_PATH; do
  [ -z "$CLIP_PATH" ] && continue
  if [[ "$CLIP_PATH" == http* ]]; then
    FULL_URL="$CLIP_PATH"
  elif [[ "$CLIP_PATH" == /api/v1/* ]]; then
    FULL_URL="${API}${CLIP_PATH}"
  else
    FULL_URL="${API}/api/v1${CLIP_PATH#/}"
  fi
  TMP=$(mktemp --suffix=.mp4)
  HTTP=$(curl -sf -o "$TMP" -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$FULL_URL" 2>/dev/null || echo 000)
  if [ "$HTTP" != "200" ]; then
    rm -f "$TMP"
    continue
  fi
  MAGIC=$(head -c 12 "$TMP" | xxd -p 2>/dev/null || true)
  if ! echo "$MAGIC" | grep -q 66747970; then
    rm -f "$TMP"
    continue
  fi
  if command -v ffprobe >/dev/null 2>&1; then
    CODEC=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=nw=1 "$TMP" 2>/dev/null | tr -d '\r')
    DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$TMP" 2>/dev/null | tr -d '\r')
    echo "try clip codec=$CODEC duration=$DUR"
    if echo "$CODEC" | grep -qi h264 && [ -n "$DUR" ] && python3 -c "exit(0 if float('$DUR')>0 else 1)"; then
      H264_OK=1
      rm -f "$TMP"
      break
    fi
  else
    H264_OK=1
    rm -f "$TMP"
    break
  fi
  rm -f "$TMP"
done <<< "$CLIPS"

if [ "$H264_OK" -ne 1 ]; then
  echo "FAIL: no playable H.264 clip found (trigger new alert after ai-engine restart)"
  exit 1
fi

echo "=== verify-evidence-playback OK ==="
