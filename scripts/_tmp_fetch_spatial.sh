#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
CAM=8ed20433-57d5-4999-a6ab-0bea028b23a3
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

curl -sf -H "X-Internal-Key: $KEY" \
  "http://127.0.0.1:8081/api/v1/internal/orgs/${ORG}/cameras/${CAM}/spatial-config" \
  -o /tmp/feu_spatial.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/feu_spatial.json"))
# may be wrapped
cfg=d.get("spatial_rules") or d.get("spatial") or d
zones=cfg.get("zones") if isinstance(cfg,dict) else []
if not zones and isinstance(d,dict):
  zones=d.get("zones") or []
print("keys", list(d.keys())[:20] if isinstance(d,dict) else type(d))
print("n_zones", len(zones or []))
for z in zones or []:
  print(" ", z.get("name"), "behavior=", z.get("behavior"), "kind=", z.get("zone_kind"), "cfg=", z.get("behavior_config"))
PY

echo "=== zones DB for cam + null cam ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT name, zone_kind, camera_id::text, is_active
FROM zones
WHERE camera_id='$CAM' OR camera_id IS NULL OR name ILIKE '%distance%' OR name ILIKE '%feux%' OR name ILIKE '%Observation%'
ORDER BY camera_id NULLS FIRST, name;
"
