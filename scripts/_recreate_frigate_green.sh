#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== frigate inspect ==="
docker inspect citevision-v2-frigate --format 'Status={{.State.Status}} Health={{if .State.Health}}{{.State.Health.Status}}{{end}} OOM={{.State.OOMKilled}} Exit={{.State.ExitCode}}'
docker logs citevision-v2-frigate --tail 40 2>&1

echo "=== recreate frigate ==="
cd "$ROOT/infra"
docker compose --env-file "$ROOT/.env" --profile frigate up -d --force-recreate frigate
cd "$ROOT"

for i in $(seq 1 60); do
  if timeout 5 curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
    echo "FRIGATE_UP $(curl -sf http://127.0.0.1:5000/api/version)"
    break
  fi
  echo "wait $i status=$(docker inspect citevision-v2-frigate --format '{{.State.Status}}' 2>/dev/null)"
  sleep 3
done

# Vite
if ! curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null; then
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  sleep 4
fi

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild -H "X-Internal-Key: $KEY" || true
echo
sleep 8
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY" || true
echo

bash scripts/health_check_all.sh
exit $?
