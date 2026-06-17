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
   e2e_wait_event "running" "person" "" && \
   e2e_assert_evidence; then
  pass "running + preuves"
else
  fail "running"
fi

# 2 face_detected
if e2e_optional_module insightface; then
  if e2e_create_rule "E2E face" "tpl-face-detected" "face_detected" "{}" "" "any" 3 && \
     e2e_wait_event "face_detected" "" "" && \
     e2e_assert_evidence; then
    pass "face_detected + preuves"
  else
    fail "face_detected"
  fi
else
  skip "face_detected (pip install insightface)"
fi

# 3 plate_detected
if e2e_optional_module paddleocr; then
  if e2e_create_rule "E2E plate" "tpl-plate-detected" "plate_detected" "{}" "" "any" 3 && \
     e2e_wait_event "plate_detected" "" "" && \
     e2e_assert_evidence; then
    pass "plate_detected + preuves"
  else
    fail "plate_detected"
  fi
else
  skip "plate_detected (pip install paddleocr)"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== E2E famille IDENTITÉ OK (skip=$SKIP) ==="
  exit 0
fi
echo "=== E2E famille IDENTITÉ FAILED ($FAIL skip=$SKIP) ==="
exit 1
