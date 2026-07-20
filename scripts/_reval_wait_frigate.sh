#!/usr/bin/env bash
set -uo pipefail
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:5000/api/version >/dev/null \
     && curl -sf http://127.0.0.1:1984/api/streams >/dev/null; then
    echo READY after ${i}x3s
    curl -sf http://127.0.0.1:5000/api/version; echo
    break
  fi
  echo wait_$i
  sleep 3
done
docker ps --filter name=frigate --format '{{.Names}} {{.Status}}'
docker ps --filter name=go2rtc --format '{{.Names}} {{.Status}}'
cd /home/gheno/citevision-v2
bash scripts/health_check_all.sh
