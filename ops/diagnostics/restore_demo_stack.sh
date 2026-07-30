#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== schemas ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c '\dn'
echo "=== citevision tables ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='citevision';"
echo "=== backend health ==="
curl -sf http://127.0.0.1:8081/health || echo FAIL
echo
echo "=== backend log tail ==="
tail -40 "$ROOT/logs/backend.log" || true

# Start rules if not up
if ! curl -sf http://127.0.0.1:8010/health >/dev/null 2>&1; then
  echo "=== start rules ==="
  if [[ -x scripts/_start-rules-engine.sh ]]; then
    bash scripts/_start-rules-engine.sh || true
  elif [[ -x rules-engine/bin/rules-engine ]]; then
    mkdir -p logs
    nohup rules-engine/bin/rules-engine > logs/rules-engine.log 2>&1 &
    echo $! > logs/rules-engine.pid
    sleep 2
  fi
fi
curl -sf http://127.0.0.1:8010/health && echo " rules OK" || echo " rules FAIL"

# Seed demo if cameras empty
CAMS=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT count(*) FROM citevision.cameras;" 2>/dev/null || echo 0)
echo "cameras=$CAMS"
if [[ "${CAMS:-0}" == "0" ]]; then
  echo "=== empty DB — seed demo ==="
  if [[ -x scripts/seed-demo-spatial.sh ]]; then
    bash scripts/seed-demo-spatial.sh 2>&1 | tail -40 || true
  fi
  if [[ -x scripts/seed-demo-rules.sh ]]; then
    bash scripts/seed-demo-rules.sh 2>&1 | tail -20 || true
  fi
  # Try go seed
  if [[ -d backend/cmd/seed-demo-rules ]]; then
    (cd backend && go run ./cmd/seed-demo-rules) 2>&1 | tail -20 || true
  fi
fi

echo "=== cameras after ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id::text, name FROM citevision.cameras LIMIT 10;" 2>&1 || true
