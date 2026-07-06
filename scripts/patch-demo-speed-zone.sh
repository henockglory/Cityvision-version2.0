#!/usr/bin/env bash
# Reset demo speed zone calibration (8 m, cooldown 2 s) + resync AI ingest.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

ORG="${DEMO_ORG_ID:-e312f375-7442-4089-8022-ed232abc09e8}"
ZONE_NAME="${DEMO_SPEED_ZONE_NAME:-Zone_distance_parcourue}"
LIMIT="${DEMO_SPEED_LIMIT_KMH:-1}"
DIST_M="${DEMO_SPEED_DISTANCE_M:-8}"
COOLDOWN="${DEMO_SPEED_COOLDOWN_SEC:-2}"
DEDUP="${DEMO_SPEED_SPATIAL_DEDUP_SEC:-2}"
RULE_NAME="${DEMO_SPEED_RULE_NAME:-Démo · Excès de vitesse}"
API_PORT="${API_PORT:-8081}"
INTERNAL_KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
PY="${ROOT}/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

echo "==> Patch zone '$ZONE_NAME': distance=${DIST_M}m cooldown=${COOLDOWN}s limit=${LIMIT} km/h"
"$PY" <<PY
import json
import os
import subprocess
import sys

org = os.environ.get("ORG", "${ORG}")
zone_name = os.environ.get("ZONE_NAME", "${ZONE_NAME}")
dist_m = float(os.environ.get("DIST_M", "${DIST_M}"))
cooldown = float(os.environ.get("COOLDOWN", "${COOLDOWN}"))
dedup = float(os.environ.get("DEDUP", "${DEDUP}"))
limit = float(os.environ.get("LIMIT", "${LIMIT}"))
edge_pattern = [dist_m, 2.0, dist_m, 2.0]

def psql_json(query: str):
    cmd = [
        "docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision",
        "-t", "-A", "-c", query,
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    if not out:
        return None
    return json.loads(out)

row = psql_json(
    f"SELECT polygon::text FROM zones WHERE org_id = '{org}'::uuid AND name = '{zone_name}' LIMIT 1;"
)
if not row:
    print(f"[FAIL] zone not found: {zone_name}", file=sys.stderr)
    sys.exit(1)

poly = row if isinstance(row, list) else json.loads(row)
for i, pt in enumerate(poly):
    if i < len(edge_pattern):
        pt["distance_to_next_m"] = edge_pattern[i]
    else:
        pt["distance_to_next_m"] = edge_pattern[i % len(edge_pattern)]

behavior = {
    "behavior": "speed_measurement",
    "config": {
        "distance_m": dist_m,
        "edge_distances_m": edge_pattern,
        "speed_limit_kmh": limit,
        "cooldown_sec": cooldown,
        "spatial_dedup_sec": dedup,
        "class_filter": "any",
    },
}

poly_json = json.dumps(poly).replace("'", "''")
beh_json = json.dumps(behavior).replace("'", "''")
subprocess.check_call([
    "docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision",
    "-v", "ON_ERROR_STOP=1", "-c",
    f"""
UPDATE zones
SET polygon = '{poly_json}'::jsonb,
    behavior_config = '{beh_json}'::jsonb,
    zone_kind = 'speed_measurement',
    updated_at = NOW()
WHERE org_id = '{org}'::uuid AND name = '{zone_name}';
""",
])
print("[OK] zone DB updated")
PY

echo "==> Rule speed_kmh=${LIMIT}"
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
SQL

echo "==> resync pipeline + keep frontend alive"
bash "$ROOT/scripts/ensure-demo-pipeline.sh"
bash "$ROOT/scripts/ensure-frontend.sh"
sleep 3

echo "==> Verify AI spatial config"
curl -sf "http://127.0.0.1:${API_PORT}/api/v1/internal/ingest/orgs/${ORG}/cameras/${DEMO_LIGNE_CAMERA_ID:-01ee632c-271c-4e66-ba98-3d1d7e430c09}/spatial-config" \
  -H "X-Internal-Key: ${INTERNAL_KEY}" | "$PY" -c "
import json,sys
d=json.load(sys.stdin)
for z in d.get('zones',[]):
    if z.get('behavior')=='speed_measurement':
        print(json.dumps(z.get('behavior_config'), indent=2))
        print('polygon distances:', [p.get('distance_to_next_m') for p in z.get('polygon',[])])
"

echo "[OK] Demo speed zone patched — expect more detections in 30–60 s on Ligne Continue"
