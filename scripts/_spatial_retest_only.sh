#!/usr/bin/env bash
# Spatial reload + 3-rule retest WITHOUT restarting API/AI.
set -euo pipefail
ROOT="/home/gheno/citevision-v2"
cd "$ROOT"
API="http://127.0.0.1:8081"
INTERNAL="changeme_internal_service_key"

echo "=== repair streams ==="
curl -sf -X POST "$API/api/v1/internal/demo/repair-streams" -H "X-Internal-Key: $INTERNAL"

echo -e "\n=== seed-demo-spatial ==="
bash scripts/seed-demo-spatial.sh

echo -e "\n=== resync-spatial ==="
curl -sf -X POST "$API/api/v1/internal/ingest/resync-spatial" -H "X-Internal-Key: $INTERNAL"
sleep 15

echo -e "\n=== verify AI health ==="
if ! curl -sf "http://127.0.0.1:8001/health" >/dev/null; then
  echo "AI down — restarting"
  python3 scripts/_restart_ai.py
fi
curl -sf "http://127.0.0.1:8001/health" | python3 -m json.tool | head -12

echo -e "\n=== verify MQTT (rules-engine dependency) ==="
if ! nc -z 127.0.0.1 1884 2>/dev/null; then
  echo "MQTT down — restarting mosquitto"
  docker restart citevision-v2-mosquitto
  sleep 5
fi

echo -e "\n=== verify rules-engine ==="
if ! curl -sf "http://127.0.0.1:8010/health" >/dev/null; then
  echo "rules-engine down — starting"
  nohup bash -lc 'cd rules-engine && go run ./cmd/rules-engine' > logs/rules-engine.log 2>&1 &
  for i in $(seq 1 30); do
    curl -sf "http://127.0.0.1:8010/health" >/dev/null && break
    sleep 2
  done
fi
curl -sf "http://127.0.0.1:8010/health" | python3 -m json.tool

echo -e "\n=== validate 3 rules ==="
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Henockglory@03}"
export TARGET_DETECTIONS=1 RULE_TIMEOUT_SEC=420 RULE_SYNC_WAIT_SEC=45
export VALIDATE_ONLY="Démo · Excès de vitesse,Démo · Téléphone au volant,Démo · Feu rouge"
export REPORT_TAG=spatial-retest
python3 scripts/validate_demo_five_rules.py
