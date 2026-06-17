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

# 4 line_cross
e2e_ensure_line "e2e-line-cross"
if e2e_create_rule "E2E line_cross" "tpl-line-cross-bidir" "line_cross" "{}" "" "person" 3 && \
   e2e_wait_event "line_cross" "person" "" && \
   e2e_assert_evidence; then
  pass "line_cross + preuves"
else
  fail "line_cross"
fi

# 5 fighting (comportement spatial multi-personnes)
if e2e_ensure_zone "e2e-fighting" "" && \
   e2e_create_rule "E2E fighting" "tpl-fighting" "fighting" '{"severity":"high"}' "e2e-fighting" "any" 3 && \
   e2e_wait_event "fighting" "" "" && \
   e2e_assert_evidence; then
  pass "fighting + preuves"
else
  fail "fighting"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== E2E famille SPATIAL OK ==="
  exit 0
fi
echo "=== E2E famille SPATIAL FAILED ($FAIL) ==="
exit 1
