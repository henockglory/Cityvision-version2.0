#!/usr/bin/env bash
set -uo pipefail
docker restart citevision-v2-go2rtc
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:1984/api/streams >/dev/null; then
    echo go2rtc_ok
    break
  fi
  # try localhost vs 127.0.0.1
  if curl -sf http://localhost:1984/api/streams >/dev/null; then
    echo go2rtc_ok_localhost
    break
  fi
  sleep 2
done
ss -ltn | grep 1984 || true
docker logs citevision-v2-go2rtc --tail 15 2>&1 | tail -15
cd /home/gheno/citevision-v2
# ensure rules engine
curl -sf http://127.0.0.1:8010/health || {
  set -a; source .env; set +a
  pkill -f rules-engine 2>/dev/null || true
  sleep 1
  setsid nohup ./rules-engine/bin/rules-engine >> logs/rules-engine.log 2>&1 &
  echo $! > logs/rules-engine.pid
  sleep 2
}
curl -sf http://127.0.0.1:8010/health; echo
bash scripts/health_check_all.sh
