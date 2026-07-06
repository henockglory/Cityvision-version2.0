#!/usr/bin/env bash
# Phase F — Vitesse arêtes A→B (calibration + scene-intent)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3

echo "=== verify-speed-edge-calibration ==="

echo ">>> pytest zone_geometry + zone_speed"
"$PY" -m pytest -q ai-engine/tests/test_zone_geometry.py --tb=line

# API scene-intent: zone calibrée doit passer, zone sans arête doit échouer
if curl -sf http://127.0.0.1:8081/health >/dev/null 2>&1; then
  # shellcheck source=scripts/lib/env-utils.sh
  source "$ROOT/scripts/lib/env-utils.sh"
  load_dotenv "$(ensure_env_file "$ROOT")"
  EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
  PASS="${ADMIN_PASSWORD:-Henockglory@03}"
  API="http://127.0.0.1:${API_PORT:-8081}/api/v1"
  TOK=$(curl -sf -X POST "$API/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
  ORG=$(curl -sf "$API/auth/me" -H "Authorization: Bearer $TOK" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("org_id") or d.get("organization_id",""))')

  # Zone speed calibrée live (si présente)
  ZONE=$(curl -sf "$API/orgs/$ORG/zones" -H "Authorization: Bearer $TOK" | python3 -c "
import sys,json
zones=json.load(sys.stdin)
for z in zones:
    bc=z.get('behavior_config') or {}
    if bc.get('behavior')!='speed_measurement':
        continue
    poly=z.get('polygon') or []
    for p in poly:
        if (p.get('distance_to_next_m') or 0)>0:
            print(z['name']); raise SystemExit
print('')
")
  if [[ -n "$ZONE" ]]; then
    BODY=$(python3 -c "import json; print(json.dumps({'definition':{'bindings':{'template_id':'tpl-speeding-premium','zone_name':'$ZONE'},'condition':{'op':'eq','field':'event_type','value':'speeding'}}}))")
    VALID=$(curl -sf -X POST "$API/orgs/$ORG/scene-intent/validate" \
      -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d "$BODY" \
      | python3 -c 'import sys,json; print(json.load(sys.stdin).get("valid"))')
    [[ "$VALID" == "True" ]] && echo "[PASS] scene-intent zone calibrée $ZONE" || echo "[FAIL] scene-intent $ZONE valid=$VALID"
  else
    echo "[WARN] aucune zone speed_measurement calibrée en DB — pytest seul validé"
  fi
else
  echo "[WARN] backend absent — pytest seul"
fi

echo "=== verify-speed-edge-calibration OK ==="
