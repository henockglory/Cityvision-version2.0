#!/usr/bin/env bash
# Sync honest-catalog changes to WSL runtime, rebuild + restart backend, verify served catalog.
set -uo pipefail
export PATH="$PATH:/usr/local/go/bin"
WIN=/mnt/c/Users/gheno/citevision
RUNTIME=~/citevision-v2

sync_file() {
  local rel="$1"
  mkdir -p "$(dirname "$RUNTIME/$rel")"
  cp "$WIN/$rel" "$RUNTIME/$rel"
  sed -i 's/\r$//' "$RUNTIME/$rel" 2>/dev/null || true
}

echo "== sync shared catalog + capabilities =="
for f in "$WIN"/shared/rule-catalog/*.json; do
  sync_file "shared/rule-catalog/$(basename "$f")"
done
sync_file shared/ai-capabilities.json

echo "== sync backend + frontend plumbing =="
sync_file backend/internal/rules/catalog.go
sync_file frontend/src/api/mappers.ts

cd "$RUNTIME" || exit 1

echo "== rebuild backend =="
if (cd backend && go build -o bin/citevision-api ./cmd/api); then
  echo BACKEND_BUILD_OK
else
  echo BACKEND_BUILD_FAIL; exit 1
fi

echo "== restart backend =="
source scripts/lib/env-utils.sh 2>/dev/null || true
ENV_FILE="$(ensure_env_file "$PWD" 2>/dev/null || echo .env)"
if command -v stop_from_pid >/dev/null 2>&1; then
  stop_from_pid logs/backend.pid 2>/dev/null || true
fi
free_port 8081 2>/dev/null || pkill -f 'bin/citevision-api' 2>/dev/null || true
sleep 1
if command -v start_bg >/dev/null 2>&1; then
  start_bg backend "$PWD/backend" "$PWD/backend/bin/citevision-api" "$PWD/logs" "$ENV_FILE"
else
  (cd backend && nohup ./bin/citevision-api > "$PWD/logs/backend.log" 2>&1 &)
fi
sleep 4

echo "== verify served catalog (honesty) =="
curl -sf http://localhost:8081/health >/dev/null && echo "backend health OK" || echo "backend DOWN"
