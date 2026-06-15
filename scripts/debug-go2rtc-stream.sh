#!/usr/bin/env bash
set -euo pipefail
echo "=== Host video ==="
ls -lah /home/gheno/citevision-v2/data/videos/ 2>&1 || ls -lah ~/citevision-v2/data/videos/ 2>&1
echo "=== Container /videos ==="
docker exec citevision-v2-go2rtc ls -lah /videos/ 2>&1
echo "=== go2rtc streams API ==="
curl -sf http://localhost:1984/api/streams | python3 -m json.tool 2>&1 | head -60
echo "=== stream.html HTTP ==="
curl -sf -o /dev/null -w "HTTP %{http_code}\n" "http://localhost:1984/stream.html?src=benedicte&mode=webrtc,mse"
