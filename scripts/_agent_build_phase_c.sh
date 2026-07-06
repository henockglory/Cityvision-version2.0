#!/usr/bin/env bash
set -euo pipefail
export PATH="${PATH}:/usr/local/go/bin:/home/gheno/go/bin"
SRC="/mnt/c/Users/gheno/citevision"
RUNTIME="${HOME}/citevision-v2"

echo "== sync Phase C backend =="
mkdir -p "${RUNTIME}/backend/internal/sceneintent"
mkdir -p "${RUNTIME}/backend/internal/capabilities"
for f in \
  backend/cmd/api/main.go \
  backend/internal/handler/api.go \
  backend/internal/handler/capabilities.go \
  backend/internal/sceneintent/intent.go \
  backend/internal/sceneintent/validate.go \
  backend/internal/capabilities/menu.go \
  backend/internal/ingest/manifest.go \
  backend/internal/ingest/orchestrator.go; do
  dest="${RUNTIME}/${f}"
  mkdir -p "$(dirname "$dest")"
  sed 's/\r$//' < "${SRC}/${f}" > "$dest"
done

echo "== sync Phase C frontend =="
for f in \
  frontend/src/api/client.ts \
  frontend/src/components/rules/RuleActivationDialog.tsx; do
  dest="${RUNTIME}/${f}"
  mkdir -p "$(dirname "$dest")"
  sed 's/\r$//' < "${SRC}/${f}" > "$dest"
done

echo "== build backend =="
cd "${RUNTIME}/backend"
go build -o bin/citevision-api ./cmd/api/
echo "BUILD OK"

echo "== restart API =="
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user restart citevision-api 2>/dev/null || true
fi
pkill -f 'bin/citevision-api' 2>/dev/null || true
sleep 1
nohup "${RUNTIME}/backend/bin/citevision-api" > "${RUNTIME}/logs/api.log" 2>&1 &
sleep 2
curl -sf http://127.0.0.1:8081/health >/dev/null && echo "API health OK" || echo "API health check pending"
