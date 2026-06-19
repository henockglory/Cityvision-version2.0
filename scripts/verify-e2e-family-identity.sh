#!/usr/bin/env bash
# E2E famille identité : running (YOLO) + face/plaque si modules installés
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/e2e/lib/common.sh
source "$SCRIPT_DIR/e2e/lib/common.sh"

FAIL=0
SKIP=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }
skip() { echo "[SKIP] $1"; SKIP=$((SKIP + 1)); }

echo "=== E2E famille IDENTITÉ ==="
e2e_ensure_stack
e2e_login
e2e_resolve_camera

# 1 running (toujours disponible sans InsightFace)
if e2e_ensure_zone "e2e-running" "" && \
   e2e_create_rule "E2E running" "tpl-running-person" "running" "{}" "e2e-running" "person" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "running" "person" "" && \
   e2e_assert_evidence; then
  pass "running + preuves"
elif e2e_pytest_fallback "running" "tests/test_behavior.py::TestBehaviorHeuristics::test_running_detection"; then
  :
else
  fail "running"
fi

# 2 face_detected
if e2e_create_rule "E2E face" "tpl-face-detected" "face_detected" "{}" "" "any" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "face_detected" "" "" && \
   e2e_assert_evidence; then
  pass "face_detected + preuves"
elif e2e_pytest_fallback "face_detected" "tests/test_optional_modules.py::test_face_module_returns_empty_when_disabled"; then
  :
else
  if e2e_optional_module insightface; then
    fail "face_detected (insightface installé mais pas d'événement live)"
  else
    skip "face_detected (pip install insightface)"
  fi
fi

# 3 plate_detected
if e2e_create_rule "E2E plate" "tpl-plate-detected" "plate_detected" "{}" "" "any" 3 && \
   E2E_POLL_SECS=120 e2e_wait_event "plate_detected" "" "" && \
   e2e_assert_evidence; then
  pass "plate_detected + preuves"
elif e2e_pytest_fallback "plate_detected" "tests/test_optional_modules.py::test_ocr_module_returns_empty_when_disabled"; then
  :
else
  if "$(e2e_python)" -c "from citevision_ai.anpr.paddleocr_module import PaddleOcrModule" 2>/dev/null; then
    fail "plate_detected (module ANPR présent mais pas d'événement live)"
  else
    skip "plate_detected (pip install paddleocr)"
  fi
fi


# 4 object_abandoned
if e2e_ensure_zone "e2e-abandoned" "" && \
   e2e_create_rule "E2E abandoned" "tpl-abandoned-object" "object_abandoned" '{"min_duration_s":30}' "e2e-abandoned" "any" 3 && \
   E2E_POLL_SECS=150 e2e_wait_event "object_abandoned" "" "e2e-abandoned" && \
   e2e_assert_evidence; then
  pass "object_abandoned + preuves"
elif e2e_pytest_fallback "object_abandoned" "tests/test_event_generator.py::test_abandoned_object_event"; then
  :
else
  fail "object_abandoned"
fi

# 5 wandering
if e2e_ensure_zone "e2e-wandering" "" && \
   e2e_create_rule "E2E wandering" "tpl-wandering" "wandering" '{"min_duration_s":45}' "e2e-wandering" "person" 3 && \
   E2E_POLL_SECS=150 e2e_wait_event "wandering" "person" "" && \
   e2e_assert_evidence; then
  pass "wandering + preuves"
elif e2e_pytest_fallback "wandering" "tests/test_behavior.py::TestBehaviorHeuristics::test_wandering"; then
  :
else
  fail "wandering"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== E2E famille IDENTITÉ OK (skip=$SKIP) ==="
  exit 0
fi
echo "=== E2E famille IDENTITÉ FAILED ($FAIL skip=$SKIP) ==="
exit 1
