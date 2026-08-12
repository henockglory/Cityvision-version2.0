#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
if ! declare -F compose_gpu_files >/dev/null 2>&1; then
  _cg_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  [[ -f "$_cg_root/scripts/lib/compose-gpu.sh" ]] || _cg_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  source "$_cg_root/scripts/lib/compose-gpu.sh"
fi
ROOT="$HOME/citevision-v2"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

echo "=== docker ==="
docker info >/dev/null 2>&1 || { echo "dockerd down — starting"; bash "$ROOT/scripts/_start_dockerd_wsl.sh" 2>/dev/null || ensure_docker_ready 90 install || true; }
docker ps -a --format '{{.Names}} {{.Status}}' | head -20

echo "=== compose up infra ==="
(cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" --profile ocr --profile frigate up -d \
  postgres redis mosquitto minio mailhog citevision-ocr go2rtc 2>&1 | tail -30)

sleep 5
echo "=== ss ports ==="
ss -ltn | grep -E ':(5433|6380|1884|9003|8181|8025|1984)\b' || echo "none"

echo "=== ensure_infra ==="
ensure_infra_host_ports || true

# If still dead, recreate all
if ! tcp_ok 127.0.0.1 6380; then
  echo "=== hard recreate redis ==="
  docker rm -f citevision-v2-redis 2>/dev/null || true
  free_port 6380 2>/dev/null || true
  (cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" up -d redis)
  sleep 3
  ss -ltn | grep 6380 || true
  docker ps --filter name=citevision-v2-redis --format '{{.Names}} {{.Status}} {{.Ports}}'
fi

ensure_infra_host_ports
echo HEAL_OK
