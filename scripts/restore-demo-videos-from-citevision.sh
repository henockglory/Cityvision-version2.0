#!/usr/bin/env bash
# Restore demo _stream.mp4 files from C:\Citevision runtime into WSL citevision-v2.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORG="${1:-e312f375-7442-4089-8022-ed232abc09e8}"
SRC="/mnt/c/Citevision/data/videos/demo/${ORG}"
DEST="${ROOT}/data/videos/demo/${ORG}"

if [[ ! -d "$SRC" ]]; then
  echo "[FAIL] Source not found: $SRC" >&2
  exit 1
fi

mkdir -p "$DEST"
echo "==> Copying demo streams: $SRC -> $DEST"
shopt -s nullglob
count=0
for f in "$SRC"/*_stream.mp4; do
  cp -a "$f" "$DEST/"
  count=$((count + 1))
  echo "  $(basename "$f")"
done

if [[ "$count" -eq 0 ]]; then
  echo "[FAIL] No *_stream.mp4 in $SRC" >&2
  exit 1
fi

echo "[OK] Copied $count file(s)"
ls -lah "$DEST"

echo "==> Restart go2rtc"
docker restart citevision-v2-go2rtc >/dev/null
sleep 5

echo "==> Files visible in container"
docker exec citevision-v2-go2rtc ls -lah "/videos/demo/${ORG}/"

echo "==> Re-register streams via backend restart"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
LOGDIR="$ROOT/logs"
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port "${API_PORT:-8081}"
sleep 2
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"
start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$LOGDIR" "$ENV_FILE"
for _ in $(seq 1 45); do
  curl -sf "http://localhost:${API_PORT:-8081}/health" >/dev/null 2>&1 && break
  sleep 2
done
sleep 3

ACTIVE=$(curl -sf "http://localhost:${API_PORT:-8081}/api/v1/orgs/${ORG}/demo/settings" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('active_go2rtc_src',''))" 2>/dev/null || true)
echo "Active stream: ${ACTIVE:-unknown}"

if [[ -n "${ACTIVE:-}" ]]; then
  echo "==> RTSP probe"
  GO2RTC_STREAM="$ACTIVE" RTSP_URL="rtsp://127.0.0.1:8554/${ACTIVE}" bash "$ROOT/scripts/validate-video-playback.sh"
fi

echo "[OK] Demo videos restored"
