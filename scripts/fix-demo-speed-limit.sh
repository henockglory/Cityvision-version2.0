#!/usr/bin/env bash
# Apply demo speed rule threshold to zone + reload spatial/AI ingest.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

ORG="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
LIMIT="${DEMO_SPEED_LIMIT_KMH:-1}"
RULE_NAME="${DEMO_SPEED_RULE_NAME:-Démo · Excès de vitesse}"
ZONE_NAME="${DEMO_SPEED_ZONE_NAME:-Zone_distance_parcourue}"

echo "==> force-spatial-reload (seed + sync)"
bash "$ROOT/scripts/force-spatial-reload.sh"

echo "==> Set rule '$RULE_NAME' speed_kmh=$LIMIT (after seed, zone DB follows on next rule sync)"
docker exec citevision-v2-postgres psql -U citevision -d citevision -v ON_ERROR_STOP=1 <<SQL
UPDATE rules
SET definition = jsonb_set(
  definition,
  '{bindings,speed_kmh}',
  to_jsonb(${LIMIT}::numeric),
  true
),
updated_at = NOW()
WHERE org_id = '${ORG}'::uuid AND name = '${RULE_NAME}';

UPDATE zones
SET behavior_config = jsonb_set(
  COALESCE(behavior_config, '{}'::jsonb),
  '{config,speed_limit_kmh}',
  to_jsonb(${LIMIT}::numeric),
  true
),
updated_at = NOW()
WHERE org_id = '${ORG}'::uuid AND name = '${ZONE_NAME}';
SQL

echo "==> resync-spatial + restart ingest (keep backend up for evidence upload)"
curl -sf -X POST "http://127.0.0.1:${API_PORT:-8081}/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: ${INTERNAL_API_KEY:-changeme_internal_service_key}" >/dev/null || true
sleep 12
bash "$ROOT/scripts/restart-ai-ingest.sh" 2>/dev/null || bash "$ROOT/scripts/restart-ai-engine.sh" 2>/dev/null || true

echo "[OK] Speed limit ${LIMIT} km/h — wait 30–60 s on Ligne Continue with rule active"
