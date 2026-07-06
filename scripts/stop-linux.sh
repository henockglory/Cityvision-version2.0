#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

LOGDIR="$ROOT/logs"

echo "=== Citevision v2 Stop (Linux/WSL) ==="

for svc in frontend ai-engine rules-engine backend watch-backend watch-ai-ingest watch-demo-stack; do
  stop_from_pid "$LOGDIR/${svc}.pid"
done

free_port 5174 5175 5176 5177
free_port 8081 8001 8010
sleep 1

echo "[INFO] Stopping Docker infrastructure..."
docker compose -f infra/docker-compose.yml down 2>/dev/null || true
echo "[OK] Stopped"
