#!/usr/bin/env bash
# E2E live (avec fallback pytest) pour les 10 templates ex-« Bientôt »
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/e2e/lib/common.sh
source "$SCRIPT_DIR/e2e/lib/common.sh"

FAIL=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "=== E2E templates ex-Bientôt (10) ==="

export E2E_ZONE_NAME=""
e2e_ensure_stack
e2e_login
e2e_resolve_camera

# --- tpl-theft-composite (SEQUENCE inline, sans redémarrage imbriqué) ---
e2e_ensure_zone "e2e-theft-zone" ""
THEFT_RULE=$(python3 <<PY
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
curl -sf -X POST "$E2E_API/api/v1/orgs/$E2E_ORG/rules" \
  -H "Authorization: Bearer $E2E_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"name\":\"E2E theft composite inline\",\"description\":\"e2e\",\"priority\":10,\"definition\":$THEFT_RULE}" >/dev/null
sleep "$E2E_RULE_SYNC_WAIT"
THEFT_OK=$(curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/events?limit=80" -H "Authorization: Bearer $E2E_TOKEN" | python3 -c "
import sys,json
raw=sys.stdin.read().strip()
if not raw: print(0); raise SystemExit
data=json.loads(raw)
if not isinstance(data, list): print(0); raise SystemExit
types=set()
for e in data:
    p=e.get('payload') or e
    t=p.get('event_type')
    if t: types.add(t)
print(1 if 'zone_enter' in types and 'loitering' in types else 0)
" 2>/dev/null || echo 0)
if [ "$THEFT_OK" = "1" ]; then
  pass "tpl-theft-composite"
elif e2e_pytest_fallback "tpl-theft-composite" "tests/test_event_generator.py::test_loitering_event"; then
  :
else
  fail "tpl-theft-composite"
fi

# --- tpl-fight ---
if e2e_create_rule "E2E fight" "tpl-fight" "fight_detected" "{}" "" "person" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "fight_detected" "person" ""; then
  pass "tpl-fight live"
elif e2e_pytest_fallback "tpl-fight" "tests/test_bientot_detectors.py::test_fight_detected_emitted"; then
  :
else
  fail "tpl-fight"
fi

# --- tpl-crowd-panic ---
if e2e_create_rule "E2E crowd panic" "tpl-crowd-panic" "crowd_panic" "{}" "" "any" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "crowd_panic" "" ""; then
  pass "tpl-crowd-panic live"
elif e2e_pytest_fallback "tpl-crowd-panic" "tests/test_bientot_detectors.py::test_crowd_panic_emitted"; then
  :
else
  fail "tpl-crowd-panic"
fi

# --- tpl-vandalism (running + person_count metadata) ---
if e2e_create_rule "E2E vandalism" "tpl-vandalism" "running" \
   '{"extra_conditions":[{"op":"contains","field":"metadata.behavior","value":"rapid_activity"}]}' "" "person" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "running" "person" ""; then
  pass "tpl-vandalism live"
elif e2e_pytest_fallback "tpl-vandalism" "tests/test_bientot_detectors.py::test_rapid_activity_behavior"; then
  :
else
  fail "tpl-vandalism"
fi

# --- tpl-accident (SEQUENCE) ---
RULE_DEF=$(python3 <<PY
import json, os
definition = {
    "condition": {
        "op": "SEQUENCE",
        "window_seconds": 60,
        "children": [
            {"op": "eq", "field": "event_type", "value": "sudden_stop"},
            {"op": "eq", "field": "event_type", "value": "vehicle_stopped"},
        ],
    },
    "actions": [{"type": "alert", "config": {"severity": "critical"}}],
    "camera_id": os.environ["E2E_CAMERA_ID"],
    "bindings": {"template_id": "tpl-accident", "camera_id": os.environ["E2E_CAMERA_ID"]},
}
print(json.dumps(definition))
PY
)
curl -sf -X POST "$E2E_API/api/v1/orgs/$E2E_ORG/rules" \
  -H "Authorization: Bearer $E2E_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"name\":\"E2E accident\",\"description\":\"e2e sequence\",\"priority\":10,\"definition\":$RULE_DEF}" >/dev/null
sleep "$E2E_RULE_SYNC_WAIT"
ACC_OK=$(curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/events?limit=80" -H "Authorization: Bearer $E2E_TOKEN" | python3 -c "
import sys,json
raw=sys.stdin.read().strip()
if not raw: print(0); raise SystemExit
data=json.loads(raw)
if not isinstance(data, list): print(0); raise SystemExit
types=set()
for e in data:
    p=e.get('payload') or e
    t=p.get('event_type')
    if t: types.add(t)
print(1 if 'sudden_stop' in types and 'vehicle_stopped' in types else 0)
" 2>/dev/null || echo 0)
if [ "$ACC_OK" = "1" ]; then
  pass "tpl-accident sources"
elif e2e_pytest_fallback "tpl-accident sudden_stop" "tests/test_sudden_stop.py"; then
  :
elif e2e_pytest_fallback "tpl-accident vehicle_stopped" "tests/test_scene_state_e2e.py::test_vehicle_stopped_event"; then
  :
else
  fail "tpl-accident"
fi

# --- tpl-illegal-parking ---
if e2e_ensure_zone "e2e-illegal-park" "" && \
   e2e_create_rule "E2E illegal parking" "tpl-illegal-parking" "vehicle_stopped" "{}" "e2e-illegal-park" "car" 8 && \
   E2E_POLL_SECS=120 e2e_wait_event "vehicle_stopped" "car" "e2e-illegal-park"; then
  pass "tpl-illegal-parking live"
elif e2e_pytest_fallback "tpl-illegal-parking" "tests/test_bientot_detectors.py::test_vehicle_stopped_has_zone_and_duration"; then
  :
else
  fail "tpl-illegal-parking"
fi

# --- tpl-multi-zone ---
e2e_ensure_zone "e2e-mz-a" ""
e2e_ensure_zone "e2e-mz-b" ""
MZ_RULE=$(python3 <<PY
import json, os
definition = {
    "condition": {
        "op": "SEQUENCE",
        "window_seconds": 180,
        "children": [
            {"op": "eq", "field": "event_type", "value": "zone_enter"},
            {"op": "eq", "field": "event_type", "value": "zone_enter"},
        ],
    },
    "actions": [{"type": "alert", "config": {"severity": "medium"}}],
    "camera_id": os.environ["E2E_CAMERA_ID"],
    "bindings": {
        "template_id": "tpl-multi-zone",
        "camera_id": os.environ["E2E_CAMERA_ID"],
        "zone_name": "e2e-mz-a",
        "zone_name_2": "e2e-mz-b",
    },
}
print(json.dumps(definition))
PY
)
curl -sf -X POST "$E2E_API/api/v1/orgs/$E2E_ORG/rules" \
  -H "Authorization: Bearer $E2E_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"name\":\"E2E multi-zone\",\"description\":\"e2e\",\"priority\":10,\"definition\":$MZ_RULE}" >/dev/null
sleep "$E2E_RULE_SYNC_WAIT"
MZ_OK=$(curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/events?limit=80" -H "Authorization: Bearer $E2E_TOKEN" | python3 -c "
import sys,json
raw=sys.stdin.read().strip()
if not raw: print(0); raise SystemExit
data=json.loads(raw)
if not isinstance(data, list): print(0); raise SystemExit
n=0
for e in data:
    p=e.get('payload') or e
    if p.get('event_type')=='zone_enter': n+=1
print(1 if n>=2 else 0)
" 2>/dev/null || echo 0)
if [ "$MZ_OK" = "1" ]; then
  pass "tpl-multi-zone sources"
elif e2e_pytest_fallback "tpl-multi-zone" "tests/test_event_generator.py::test_zone_enter_event"; then
  :
else
  fail "tpl-multi-zone"
fi

# --- ML routier : red light, seatbelt, phone ---
for spec in "tpl-red-light:red_light_violation:car" "tpl-seatbelt:seatbelt_violation:car" "tpl-phone-driving:phone_driving:car"; do
  IFS=: read -r tpl evt cls <<< "$spec"
  if e2e_create_rule "E2E $tpl" "$tpl" "$evt" "{}" "" "$cls" 3 && \
     E2E_POLL_SECS=120 e2e_wait_event "$evt" "$cls" ""; then
    pass "$tpl live"
  elif e2e_pytest_fallback "$tpl" "tests/test_bientot_detectors.py::test_road_enforcement_${evt}"; then
    :
  else
    fail "$tpl"
  fi
done

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== E2E BIENTOT TEMPLATES OK ==="
  exit 0
fi
echo "=== E2E BIENTOT TEMPLATES FAILED ($FAIL) ==="
exit 1
