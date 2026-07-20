#!/usr/bin/env bash
set -uo pipefail
cd /home/gheno/citevision-v2/infra
export VIDEOS_PATH=/home/gheno/citevision-v2/data/videos
export GO2RTC_WEBRTC_PORT=8565
# Also put in infra/.env for compose
grep -q '^VIDEOS_PATH=' .env 2>/dev/null && sed -i 's|^VIDEOS_PATH=.*|VIDEOS_PATH=/home/gheno/citevision-v2/data/videos|' .env \
  || echo 'VIDEOS_PATH=/home/gheno/citevision-v2/data/videos' >> .env
grep -q '^GO2RTC_WEBRTC_PORT=' .env 2>/dev/null || echo 'GO2RTC_WEBRTC_PORT=8565' >> .env

docker rm -f citevision-v2-go2rtc 2>/dev/null || true
docker compose --env-file .env up -d go2rtc
sleep 3
docker inspect citevision-v2-go2rtc --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
docker exec citevision-v2-go2rtc ls /videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/ | head
cd /home/gheno/citevision-v2
bash scripts/ensure-demo-streams.sh
sleep 2
timeout 10 ffprobe -rtsp_transport tcp -i 'rtsp://127.0.0.1:8554/demo-74d51ead-e774ae7a' 2>&1 | tail -8
bash scripts/health_check_all.sh | tail -20
