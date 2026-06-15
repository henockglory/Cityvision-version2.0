#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source "$ROOT/scripts/lib/env-utils.sh"

bash "$ROOT/scripts/ensure-demo-video.sh"
load_dotenv "$ROOT/.env"

echo "==> Recreating go2rtc with VIDEOS_PATH=${VIDEOS_PATH}"
docker compose -f infra/docker-compose.yml --env-file "$ROOT/.env" up -d --force-recreate go2rtc
sleep 4

echo "==> Ports go2rtc (1984=API, 8554=RTSP, 8555=WebRTC média)"
if ! docker port citevision-v2-go2rtc 8555/tcp 2>/dev/null | grep -q .; then
  echo "[FAIL] Port 8555/tcp non exposé — écran noir WebRTC dans Chrome" >&2
  echo "       Vérifiez infra/docker-compose.yml et relancez ce script." >&2
  exit 1
fi
docker port citevision-v2-go2rtc 1984 8554 8555 2>/dev/null || true

docker exec citevision-v2-go2rtc ls -lah /videos/ | grep -E 'benedicte|total' || true
curl -sf http://localhost:1984/api/streams | python3 -m json.tool | head -30
