#!/usr/bin/env bash
set -euo pipefail
SRC="/mnt/c/Users/gheno/citevision"
RUNTIME="${HOME}/citevision-v2"
export PATH="${PATH}:/usr/local/go/bin:/home/gheno/go/bin"

sync_file() {
  local f="$1"
  local dest="${RUNTIME}/${f}"
  mkdir -p "$(dirname "$dest")"
  sed 's/\r$//' < "${SRC}/${f}" > "$dest"
}

echo "== Phase D sync =="
for f in \
  backend/cmd/api/main.go \
  backend/internal/aimodels/pack.go \
  backend/internal/handler/aimodels.go \
  frontend/src/api/client.ts \
  frontend/src/hooks/api/queries.ts \
  frontend/src/pages/SystemHealth.tsx \
  frontend/src/i18n/fr.json \
  frontend/src/i18n/en.json \
  scripts/verify-e2e-disponibles.sh \
  shared/ai-stack-registry.json \
  shared/ai-models.json; do
  sync_file "$f"
done
chmod +x "${RUNTIME}/scripts/verify-e2e-disponibles.sh"

echo "== build backend =="
cd "${RUNTIME}/backend"
go build -o bin/citevision-api ./cmd/api/
echo "BUILD OK"

echo "== restart stack =="
cd "${RUNTIME}"
bash scripts/restart-api-frontend.sh 2>&1 | tail -12
