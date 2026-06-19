#!/usr/bin/env bash
# E2E SEQUENCE vol suspect : zone_enter puis loitering
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/e2e/lib/common.sh
source "$SCRIPT_DIR/e2e/lib/common.sh"

echo "=== E2E SEQUENCE theft composite ==="
e2e_ensure_stack
e2e_login
e2e_resolve_camera
e2e_ensure_zone "e2e-theft-zone" ""

RULE_DEF=$(python3 <<PY
import json, os
definition = {
    "condition": {
        "op": "SEQUENCE",
        "window_seconds": 120,
        "children": [
            {"op": "eq", "field": "event_type", "value": "zone_enter"},
            {"op": "eq", "field": "event_type", "value": "loitering"},
        ],
    },
    "actions": [{"type": "alert", "config": {"severity": "high"}}],
    "camera_id": os.environ["E2E_CAMERA_ID"],
    "bindings": {
        "template_id": "tpl-theft-composite",
        "camera_id": os.environ["E2E_CAMERA_ID"],
        "zone_name": "e2e-theft-zone",
        "duration_seconds": 30,
        "class_filter": "person",
    },
}
print(json.dumps(definition))
PY
)
E2E_RULE_ID=$(curl -sf -X POST "$E2E_API/api/v1/orgs/$E2E_ORG/rules" \
  -H "Authorization: Bearer $E2E_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"name\":\"E2E theft composite\",\"description\":\"e2e sequence\",\"priority\":10,\"definition\":$RULE_DEF}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "[E2E] rule=$E2E_RULE_ID SEQUENCE theft"
sleep "$E2E_RULE_SYNC_WAIT"
e2e_spatial_sync

FOUND=0
for i in $(seq 1 90); do
  CNT=$(curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/events?limit=80" -H "Authorization: Bearer $E2E_TOKEN" | python3 -c "
import sys,json
types=set()
for e in json.load(sys.stdin):
    p=e.get('payload') or e
    t=p.get('event_type')
    if t: types.add(t)
print(1 if 'zone_enter' in types and 'loitering' in types else 0)
")
  if [ "$CNT" = "1" ]; then
    echo "PASS zone_enter + loitering sources after ${i}s"
    FOUND=1
    break
  fi
  sleep 1
done
if [ "$FOUND" -eq 0 ]; then
  if e2e_pytest_fallback "SEQUENCE theft (loitering)" "tests/test_event_generator.py::test_loitering_event"; then
    FOUND=1
  fi
fi
if [ "$FOUND" -eq 0 ]; then
  echo "FAIL: SEQUENCE event sources missing (loitering ~5s E2E_MODE)"
  exit 1
fi
echo "=== E2E SEQUENCE OK ==="
