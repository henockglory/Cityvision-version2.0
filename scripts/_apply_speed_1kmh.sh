#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

ORG="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"

echo "==> DB: speed limit 1 km/h + cooldown 5s"
docker exec citevision-v2-postgres psql -U citevision -d citevision -v ON_ERROR_STOP=1 <<SQL
UPDATE rules
SET definition = jsonb_set(definition, '{bindings,speed_kmh}', '1'::jsonb, true),
    updated_at = NOW()
WHERE org_id = '${ORG}'::uuid AND name = 'Démo · Excès de vitesse';

UPDATE zones
SET behavior_config = jsonb_set(
  jsonb_set(COALESCE(behavior_config, '{}'::jsonb), '{config,speed_limit_kmh}', '1'::jsonb, true),
  '{config,cooldown_sec}', '5'::jsonb, true
),
updated_at = NOW()
WHERE org_id = '${ORG}'::uuid AND name = 'Zone_distance_parcourue';
SQL

echo "==> restart-ai-ingest"
bash "$ROOT/scripts/restart-ai-ingest.sh"

echo "==> verify AI spatial"
sleep 8
curl -sf "http://127.0.0.1:8001/cameras/01ee632c-271c-4e66-ba98-3d1d7e430c09/spatial" | python3 -m json.tool
