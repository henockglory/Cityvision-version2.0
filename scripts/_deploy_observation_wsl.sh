#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
DEST=~/citevision-v2
mkdir -p "$DEST"
for d in backend rules-engine frontend shared scripts ai-engine; do
  rsync -a \
    --exclude node_modules --exclude .venv --exclude dist --exclude bin \
    "$WIN/$d/" "$DEST/$d/"
done
find "$DEST" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.go' -o -name '*.sql' \) -exec sed -i 's/\r$//' {} + 2>/dev/null || true
echo "[OK] Synced to $DEST"

cd "$DEST"
export PATH="$PATH:/usr/local/go/bin"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

echo "[INFO] Building backend + rules-engine..."
(cd backend && go build -o bin/citevision-api ./cmd/api)
(cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine)

echo "[INFO] Restarting stack..."
bash scripts/restart-api-frontend.sh

echo "[INFO] Health checks..."
curl -sf "http://127.0.0.1:${API_PORT:-8081}/health" | head -c 200 || true
echo ""
curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" | head -c 200 || true
echo ""
echo "[OK] Deploy observation complete"
