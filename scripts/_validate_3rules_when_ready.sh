#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/gheno/citevision-v2"
cd "$ROOT"

wait_url() {
  local url="$1" n="${2:-40}"
  for _ in $(seq 1 "$n"); do
    curl -sf "$url" >/dev/null && return 0
    sleep 2
  done
  echo "timeout: $url" >&2
  return 1
}

# Ensure MQTT for rules-engine
if ! nc -z 127.0.0.1 1884 2>/dev/null; then
  docker restart citevision-v2-mosquitto
  sleep 5
fi

if ! curl -sf http://127.0.0.1:8081/health >/dev/null; then
  python3 scripts/_restart_frigate_demo.py
fi
if ! curl -sf http://127.0.0.1:8001/health >/dev/null; then
  python3 scripts/_restart_ai.py
fi
if ! curl -sf http://127.0.0.1:8010/health >/dev/null; then
  export PATH=/usr/local/go/bin:$PATH
  set -a; source .env; set +a
  nohup go run ./rules-engine/cmd/rules-engine > logs/rules-engine.log 2>&1 &
  wait_url http://127.0.0.1:8010/health 30
fi

wait_url http://127.0.0.1:8081/health
wait_url http://127.0.0.1:8001/health
wait_url http://127.0.0.1:8010/health

export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Henockglory@03}"
export TARGET_DETECTIONS=1 RULE_TIMEOUT_SEC=420 RULE_SYNC_WAIT_SEC=45
export VALIDATE_ONLY="Démo · Excès de vitesse,Démo · Téléphone au volant,Démo · Feu rouge"
export REPORT_TAG=spatial-retest
python3 scripts/validate_demo_five_rules.py
