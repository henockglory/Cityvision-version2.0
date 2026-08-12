
# shellcheck disable=SC1091
if ! declare -F compose_gpu_files >/dev/null 2>&1; then
  _cg_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  [[ -f "$_cg_root/scripts/lib/compose-gpu.sh" ]] || _cg_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  source "$_cg_root/scripts/lib/compose-gpu.sh"
fi
#!/bin/bash
set -e
cd ~/citevision-v2
export PATH="$PATH:/usr/local/go/bin"

find scripts -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true

# WSL: pas de systemd — démarrer dockerd si absent
if ! docker info >/dev/null 2>&1; then
  sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
  sleep 4
fi
if ! docker info >/dev/null 2>&1; then
  echo "[FAIL] Docker daemon not running" >&2
  exit 1
fi

source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
ensure_demo_runtime_env "$PWD" "$ENV_FILE" 2>/dev/null || true
ensure_demo_validation_env "$PWD" "$ENV_FILE" 2>/dev/null || true
load_dotenv "$ENV_FILE"

echo "=== Docker compose up (core + frigate + ocr) ==="
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" \
  --profile frigate --profile ocr up -d
# Explicit frigate bring-up if profile missed the container
if ! docker ps --format '{{.Names}}' | grep -q citevision-v2-frigate; then
  docker compose $(compose_gpu_files infra/) --env-file "$ENV_FILE" --profile frigate up -d frigate || true
fi
sleep 5
docker ps --format 'table {{.Names}}\t{{.Status}}'
