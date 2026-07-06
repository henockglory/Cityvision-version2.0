#!/bin/bash
# Suite du déploiement une fois Docker infra OK
set -euo pipefail
cd ~/citevision-v2
export PATH="$PATH:/usr/local/go/bin"
find scripts -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true

grep -q '^AI_REQUIRE_ALL_MODELS=' .env \
  && sed -i 's/^AI_REQUIRE_ALL_MODELS=.*/AI_REQUIRE_ALL_MODELS=false/' .env \
  || echo 'AI_REQUIRE_ALL_MODELS=false' >> .env

echo "=== AI pip (sans torch CUDA) ==="
ai-engine/.venv/bin/pip install -q --upgrade pip
ai-engine/.venv/bin/pip install -q -e "ai-engine/." 2>&1 | tail -3 || true

echo "=== Modèles ==="
bash scripts/install-ai-models.sh 2>&1 | tail -5 || true

echo "=== Build + start ==="
mkdir -p backend/bin logs
(cd backend && go build -o bin/citevision-api ./cmd/api)
bash scripts/restart-api-frontend.sh 2>&1 | tail -25

echo "=== HEALTH ==="
curl -sf http://localhost:8081/health && echo " backend OK" || echo " backend FAIL"
curl -sf http://localhost:8001/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('AI',d.get('status'))" 2>/dev/null || echo " AI FAIL"
curl -sf http://localhost:8010/health && echo " rules OK" || echo " rules FAIL"
curl -sf -o /dev/null -w "frontend %{http_code}\n" http://localhost:5174/
