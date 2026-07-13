#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
export PATH="$PATH:/usr/local/go/bin"
echo "=== Build backend ==="
mkdir -p backend/bin rules-engine/bin logs
(cd backend && go build -o bin/citevision-api ./cmd/api)
(cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine)
echo "=== AI engine editable install ==="
if [[ -x ai-engine/.venv/bin/pip ]]; then
  ai-engine/.venv/bin/pip install -q -e ai-engine/. 2>/dev/null || true
fi
echo "=== Restart API + frontend ==="
bash scripts/restart-api-frontend.sh 2>&1 | tail -40
echo "=== Health ==="
curl -sf http://127.0.0.1:8081/health/platform | head -c 400 || curl -sf http://127.0.0.1:8081/health
echo ""
curl -sf -o /dev/null -w "frontend HTTP %{http_code}\n" http://127.0.0.1:5174/
