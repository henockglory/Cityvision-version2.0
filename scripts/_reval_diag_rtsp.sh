#!/usr/bin/env bash
set -uo pipefail
echo "=== streams api ==="
curl -sf http://127.0.0.1:1984/api/streams | python3 -m json.tool 2>/dev/null | head -80
echo "=== video files ==="
ls -la /home/gheno/citevision-v2/infra/data/videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/ 2>/dev/null | head -20
docker exec citevision-v2-go2rtc ls -la /videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/ 2>/dev/null | head -20
echo "=== rtsp probe ==="
timeout 8 ffprobe -rtsp_transport tcp -i 'rtsp://127.0.0.1:8554/demo-74d51ead-e774ae7a' 2>&1 | tail -25
echo "=== go2rtc logs ==="
docker logs citevision-v2-go2rtc --tail 30 2>&1 | tail -30
echo "=== ensure streams ==="
cd /home/gheno/citevision-v2
bash scripts/ensure-demo-streams.sh || true
sleep 2
timeout 8 ffprobe -rtsp_transport tcp -i 'rtsp://127.0.0.1:8554/demo-74d51ead-e774ae7a' 2>&1 | tail -15
