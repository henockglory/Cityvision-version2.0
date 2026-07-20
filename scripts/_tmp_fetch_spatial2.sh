#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
CAM=8ed20433-57d5-4999-a6ab-0bea028b23a3
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
URL="http://127.0.0.1:8081/api/v1/internal/orgs/${ORG}/cameras/${CAM}/spatial-config"
code=$(curl -sS -o /tmp/feu_spatial.json -w '%{http_code}' -H "X-Internal-Key: $KEY" "$URL" || echo err)
echo "HTTP $code"
wc -c /tmp/feu_spatial.json 2>/dev/null || true
python3 - <<'PY'
import json
from pathlib import Path
p=Path("/tmp/feu_spatial.json")
if not p.exists() or p.stat().st_size==0:
  print("empty"); raise SystemExit
raw=p.read_text()
print(raw[:300])
d=json.loads(raw)
# unwrap common envelopes
for k in ("spatial_rules","spatial","config","data"):
  if isinstance(d.get(k), dict) and "zones" in d[k]:
    d=d[k]; break
zones=d.get("zones") or []
print("n_zones", len(zones))
for z in zones:
  print(z.get("name"), z.get("behavior"), z.get("zone_kind"))
PY
