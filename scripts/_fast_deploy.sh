#!/bin/bash
# Déploiement rapide après réinstall WSL — sans attendre torch CUDA
set -euo pipefail
cd ~/citevision-v2
export PATH="$PATH:/usr/local/go/bin"
find scripts -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true

echo "=== 1. Arrêt setup bloqué ==="
pkill -f 'scripts/setup-wsl.sh' 2>/dev/null || true
pkill -f 'pip install.*torch' 2>/dev/null || true
sleep 2

echo "=== 2. Docker ==="
if ! command -v docker >/dev/null; then
  echo "Docker manquant — lancez scripts/_install_docker.sh en root"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin manquant"
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
  sleep 5
fi

source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

# Mode démo rapide sans bloquer sur PaddleOCR/CUDA
grep -q '^AI_REQUIRE_ALL_MODELS=' "$ENV_FILE" \
  && sed -i 's/^AI_REQUIRE_ALL_MODELS=.*/AI_REQUIRE_ALL_MODELS=false/' "$ENV_FILE" \
  || echo 'AI_REQUIRE_ALL_MODELS=false' >> "$ENV_FILE"

echo "=== 3. Infra Docker ==="
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" up -d
sleep 8
docker ps --format '{{.Names}}' | head -10

echo "=== 4. AI venv minimal ==="
if [[ ! -x ai-engine/.venv/bin/python3 ]]; then
  python3.12 -m venv ai-engine/.venv
fi
# pip de base sans torch CUDA (ultralytics onnxruntime suffisent pour démarrer)
ai-engine/.venv/bin/pip install -q --upgrade pip
ai-engine/.venv/bin/pip install -q -e "ai-engine/.[dev]" 2>/dev/null \
  || ai-engine/.venv/bin/pip install -q -e ai-engine/

echo "=== 5. Modèles IA (si manquants) ==="
bash scripts/install-ai-models.sh 2>/dev/null || true

echo "=== 6. Backend build ==="
mkdir -p backend/bin logs
(cd backend && go build -o bin/citevision-api ./cmd/api)

echo "=== 7. Démarrage stack ==="
bash scripts/restart-api-frontend.sh 2>&1 | tail -30

echo ""
echo "=== HEALTH ==="
curl -sf http://localhost:8081/health && echo " backend OK" || echo " backend FAIL"
curl -sf http://localhost:8001/health | head -c 200; echo
curl -sf http://localhost:8010/health && echo " rules OK" || echo " rules FAIL"
curl -sf -o /dev/null -w "frontend HTTP %{http_code}\n" http://localhost:5174/
