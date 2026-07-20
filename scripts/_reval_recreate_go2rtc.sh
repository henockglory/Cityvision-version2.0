#!/usr/bin/env bash
set -uo pipefail
cd /home/gheno/citevision-v2/infra
# Frigate host-net already binds 8555 — use alternate webrtc port for demo go2rtc
export GO2RTC_WEBRTC_PORT=8565
docker rm -f citevision-v2-go2rtc 2>/dev/null || true
docker compose up -d go2rtc
sleep 4
docker inspect citevision-v2-go2rtc --format 'status={{.State.Status}} ports={{json .NetworkSettings.Ports}}'
ss -ltn | grep -E '1984|8554|8565' || true
curl -sf http://127.0.0.1:1984/api/streams | head -c 300; echo
# ensure streams
cd /home/gheno/citevision-v2
if [ -x scripts/ensure-demo-streams.sh ]; then
  bash scripts/ensure-demo-streams.sh || true
fi
bash scripts/health_check_all.sh
