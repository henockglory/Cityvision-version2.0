#!/bin/bash
set -e
cd ~/citevision-v2
export PATH="$PATH:/usr/local/go/bin"

pkill -f 'pip install.*torch' 2>/dev/null || true
pkill -f 'restart-api-frontend' 2>/dev/null || true
sleep 2

grep -q '^AI_REQUIRE_ALL_MODELS=' .env \
  && sed -i 's/^AI_REQUIRE_ALL_MODELS=.*/AI_REQUIRE_ALL_MODELS=false/' .env \
  || echo 'AI_REQUIRE_ALL_MODELS=false' >> .env
export AI_REQUIRE_ALL_MODELS=false

echo "=== AI engine ==="
pkill -f uvicorn 2>/dev/null || true
sleep 1
nohup ai-engine/.venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port 8001 >> logs/ai-engine.log 2>&1 &
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 5
  curl -sf http://localhost:8001/health >/dev/null && break
done
curl -sf http://localhost:8001/health | head -c 150 || echo AI_FAIL

echo ""
echo "=== Rules engine ==="
if [[ -x rules-engine/bin/rules-engine ]]; then
  pkill -f rules-engine 2>/dev/null || true
  nohup rules-engine/bin/rules-engine >> logs/rules-engine.log 2>&1 &
  sleep 3
  curl -sf http://localhost:8010/health && echo " rules_ok" || echo "rules_fail"
else
  echo "rules binary missing — build needed"
  (cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine/) 2>/dev/null || true
  nohup rules-engine/bin/rules-engine >> logs/rules-engine.log 2>&1 &
  sleep 3
  curl -sf http://localhost:8010/health && echo " rules_ok" || echo "rules_fail"
fi

echo "=== Frontend ==="
bash scripts/ensure-frontend.sh 2>&1 | tail -3
sleep 3
curl -sf -o /dev/null -w "frontend HTTP %{http_code}\n" http://localhost:5174/

echo "=== DONE ==="
curl -sf http://localhost:8081/health && echo " backend OK"
