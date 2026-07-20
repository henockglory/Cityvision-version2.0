#!/usr/bin/env bash
# Relance complète stack démo + validation Vitesse / Téléphone / Feu rouge.
set -euo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:${PATH:-}"

ROOT="${CITEVISION_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOG="$ROOT/logs/full-restart-demo-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== $(date -Iseconds) FULL RESTART DEMO ==="
echo "LOG=$LOG"

echo "=== 1/6 Docker Engine + compose ==="
ensure_docker_ready 120
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" --profile frigate up -d
sleep 8
docker ps --format 'table {{.Names}}\t{{.Status}}' | head -12

echo "=== 2/6 Backend + IA + frontend + pipeline ==="
bash "$ROOT/scripts/restart-api-frontend.sh"

echo "=== 3/6 rules-engine (si absent) ==="
if ! curl -sf http://127.0.0.1:8010/health >/dev/null; then
  bash "$ROOT/scripts/_start-rules-engine.sh"
fi
curl -sf http://127.0.0.1:8010/health | python3 -m json.tool || true

echo "=== 4/6 Demo streams + Frigate rebuild ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/demo/repair-streams" \
  -H "X-Internal-Key: $KEY" | python3 -m json.tool || true
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: $KEY" -w "\nrebuild_http=%{http_code}\n" -o /tmp/frigate_rebuild.json || true
docker restart citevision-v2-frigate citevision-v2-go2rtc 2>/dev/null || true
sleep 12

echo "=== 5/6 Spatial démo + règles actives ==="
if [[ -x "$ROOT/scripts/seed-demo-spatial.sh" ]]; then
  bash "$ROOT/scripts/seed-demo-spatial.sh" || true
fi
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: $KEY" >/dev/null || true
python3 "$ROOT/scripts/enable-demo-rules.py" || true
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=true, updated_at=NOW() WHERE name LIKE 'Démo%';" 2>/dev/null || true

echo "=== 6/6 Santé stack ==="
for u in http://127.0.0.1:8081/health http://127.0.0.1:8001/health http://127.0.0.1:8010/health http://127.0.0.1:8081/health/frigate; do
  echo -n "$u -> "
  curl -sf "$u" >/dev/null && echo OK || echo FAIL
done
grep -E '^(EVIDENCE_BACKEND|FRIGATE_EVIDENCE|FRIGATE_ENABLED)' "$ENV_FILE" || true
echo "UI: http://localhost:5174/demo"
echo "[OK] stack relancée — lancer validation 3 règles"
