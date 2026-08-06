#!/usr/bin/env bash
# Wait until backend + Frigate + AI are HTTP-ready.
set -euo pipefail
for i in $(seq 1 30); do
  b=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8081/healthz 2>/dev/null || echo 000)
  f=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:5000/api/version 2>/dev/null || echo 000)
  a=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8001/health 2>/dev/null || echo 000)
  echo "try $i backend=$b frigate=$f ai=$a"
  if [ "$b" = "200" ] && [ "$f" = "200" ] && [ "$a" = "200" ]; then
    echo READY
    exit 0
  fi
  sleep 5
done
echo NOT_READY
exit 1
