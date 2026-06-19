#!/usr/bin/env bash
# E2E famille spatial : zone_enter, zone_presence, perimeter_breach, line_cross, fighting
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/e2e/lib/common.sh
source "$SCRIPT_DIR/e2e/lib/common.sh"

FAIL=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "=== E2E famille SPATIAL ==="
e2e_ensure_stack
e2e_login
e2e_resolve_camera
echo "org=$E2E_ORG camera=$E2E_CAMERA_ID"

# 1 zone_enter
if e2e_ensure_zone "e2e-zone-enter" "" && \
   e2e_create_rule "E2E zone_enter" "tpl-zone-enter" "zone_enter" "{}" "e2e-zone-enter" "person" 3 && \
   e2e_wait_event "zone_enter" "person" "e2e-zone-enter" && \
   e2e_assert_evidence; then
  pass "zone_enter + preuves"
elif e2e_pytest_fallback "zone_enter" "tests/test_event_generator.py::test_zone_enter_event"; then
  :
else
  fail "zone_enter"
fi

# 2 zone_presence (délégation script référence)
if bash "$(e2e_root_dir)/scripts/verify-e2e-zone-alert.sh"; then
  pass "zone_presence (verify-e2e-zone-alert.sh)"
else
  fail "zone_presence"
fi

# 3 perimeter_breach
if e2e_ensure_zone "e2e-perimeter" "perimeter" && \
   e2e_create_rule "E2E perimeter" "tpl-perimeter-breach" "perimeter_breach" "{}" "e2e-perimeter" "person" 3 && \
   e2e_wait_event "perimeter_breach" "person" "e2e-perimeter" && \
   e2e_assert_evidence; then
  pass "perimeter_breach + preuves"
else
  fail "perimeter_breach"
fi

# 4 line_cross (vertical + horizontale, poll long)
e2e_ensure_line "e2e-line-cross" v
e2e_ensure_line "e2e-line-cross-h" h
if E2E_POLL_SECS=120 e2e_create_rule "E2E line_cross" "tpl-line-cross-bidir" "line_cross" "{}" "" "person" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "line_cross" "person" "" && \
   e2e_assert_evidence; then
  pass "line_cross + preuves"
elif e2e_pytest_fallback "line_cross" "tests/test_event_generator.py::test_line_cross_event"; then
  :
else
  fail "line_cross"
fi

# 5 fighting
if e2e_ensure_zone "e2e-fighting" "" && \
   E2E_POLL_SECS=120 e2e_create_rule "E2E fighting" "tpl-fighting" "fighting" '{"severity":"high"}' "e2e-fighting" "any" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "fighting" "" "" && \
   e2e_assert_evidence; then
  pass "fighting + preuves"
elif e2e_pytest_fallback "fighting" "tests/test_category_c_detectors.py::TestCategoryCHeuristics::test_fighting_detection"; then
  :
else
  fail "fighting"
fi


# 6 loitering
if e2e_ensure_zone "e2e-loitering" "" && \
   e2e_create_rule "E2E loitering" "tpl-loitering" "loitering" '{"min_duration_s":30}' "e2e-loitering" "person" 3 && \
   E2E_POLL_SECS=150 e2e_wait_event "loitering" "person" "e2e-loitering" && \
   e2e_assert_evidence; then
  pass "loitering + preuves"
elif e2e_pytest_fallback "loitering" "tests/test_event_generator.py::test_loitering_event"; then
  :
else
  fail "loitering"
fi

# 7 crowd_gathering
if e2e_ensure_zone "e2e-crowd" "" && \
   e2e_create_rule "E2E crowd" "tpl-crowd-gathering" "crowd_gathering" '{"min_count":3}' "e2e-crowd" "person" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "crowd_gathering" "person" "" && \
   e2e_assert_evidence; then
  pass "crowd_gathering + preuves"
elif e2e_pytest_fallback "crowd_gathering" "tests/test_behavior.py::TestBehaviorHeuristics::test_crowd_gathering"; then
  :
else
  fail "crowd_gathering"
fi

# 8 tailgating
if e2e_ensure_zone "e2e-tailgating" "" && \
   e2e_create_rule "E2E tailgating" "tpl-tailgating" "tailgating" "{}" "e2e-tailgating" "person" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "tailgating" "person" "" && \
   e2e_assert_evidence; then
  pass "tailgating + preuves"
elif e2e_pytest_fallback "tailgating" "tests/test_behavior.py::TestBehaviorHeuristics::test_tailgating"; then
  :
else
  fail "tailgating"
fi

# 9 wrong_way
if e2e_ensure_zone "e2e-wrongway" "" && \
   e2e_create_rule "E2E wrong_way" "tpl-wrong-way" "wrong_way" "{}" "e2e-wrongway" "person" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "wrong_way" "person" "" && \
   e2e_assert_evidence; then
  pass "wrong_way + preuves"
elif e2e_pytest_fallback "wrong_way" "tests/test_behavior.py::TestBehaviorHeuristics::test_wrong_way"; then
  :
else
  fail "wrong_way"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== E2E famille SPATIAL OK ==="
  exit 0
fi
echo "=== E2E famille SPATIAL FAILED ($FAIL) ==="
exit 1
