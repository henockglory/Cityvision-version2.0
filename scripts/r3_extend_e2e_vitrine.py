#!/usr/bin/env python3
"""
R3 – Extend E2E vitrine coverage:
  1. Add loitering, crowd_gathering, tailgating, wrong_way, abandoned tests to family scripts
  2. Add vitrine template→script mappings to coverage matrix
"""
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 1. Extend verify-e2e-family-spatial.sh with loitering, crowd_gathering, 
#    tailgating, wrong_way tests
# ──────────────────────────────────────────────────────────────────────────────
spatial_script = Path("scripts/verify-e2e-family-spatial.sh")
spatial_content = spatial_script.read_text(encoding="utf-8")

SPATIAL_ADDITIONS = r"""
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

"""

if "loitering" not in spatial_content:
    # Insert before the final pass/fail summary block
    ANCHOR = 'echo ""\nif [ "$FAIL" -eq 0 ]; then\n  echo "=== E2E famille SPATIAL OK ==="\n  exit 0\nfi\necho "=== E2E famille SPATIAL FAILED ($FAIL) ==="\nexit 1'
    spatial_content = spatial_content.replace(ANCHOR, SPATIAL_ADDITIONS + ANCHOR)
    spatial_script.write_text(spatial_content, encoding="utf-8")
    print("Extended verify-e2e-family-spatial.sh with loitering, crowd, tailgating, wrong_way")
else:
    print("family-spatial already has loitering")

# ──────────────────────────────────────────────────────────────────────────────
# 2. Extend verify-e2e-family-identity.sh with abandoned, wandering
# ──────────────────────────────────────────────────────────────────────────────
identity_script = Path("scripts/verify-e2e-family-identity.sh")
identity_content = identity_script.read_text(encoding="utf-8")

IDENTITY_ADDITIONS = r"""
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

"""

if "object_abandoned" not in identity_content:
    ANCHOR = 'echo ""\nif [ "$FAIL" -eq 0 ]; then\n  echo "=== E2E famille IDENTITÉ OK (skip=$SKIP) ==="\n  exit 0\nfi\necho "=== E2E famille IDENTITÉ FAILED ($FAIL skip=$SKIP) ==="\nexit 1'
    identity_content = identity_content.replace(ANCHOR, IDENTITY_ADDITIONS + ANCHOR)
    identity_script.write_text(identity_content, encoding="utf-8")
    print("Extended verify-e2e-family-identity.sh with abandoned, wandering")
else:
    print("family-identity already has object_abandoned")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Update E2E_SCRIPTS mappings in matrix generator for all vitrine rules
# ──────────────────────────────────────────────────────────────────────────────
matrix_script = Path("scripts/generate-rule-coverage-matrix.py")
matrix_content = matrix_script.read_text(encoding="utf-8")

OLD_VITRINE = '''    "tpl-theft-composite": "verify-e2e-sequence-theft.sh",'''
NEW_VITRINE = '''    "tpl-theft-composite": "verify-e2e-sequence-theft.sh",
    # Vitrine démo — règles spatiales supplémentaires
    "tpl-loitering": "verify-e2e-family-spatial.sh",
    "tpl-crowd-gathering": "verify-e2e-family-spatial.sh",
    "tpl-tailgating": "verify-e2e-family-spatial.sh",
    "tpl-wrong-way": "verify-e2e-family-spatial.sh",
    # Vitrine démo — identité/comportement supplémentaires
    "tpl-abandoned-object": "verify-e2e-family-identity.sh",
    "tpl-wandering": "verify-e2e-family-identity.sh",
    "tpl-intrusion": "verify-e2e-family-spatial.sh",
    "tpl-industrial-intrusion": "verify-e2e-family-spatial.sh",
    "tpl-zone-exit": "verify-e2e-family-spatial.sh",
    "tpl-line-cross-entry": "verify-e2e-family-spatial.sh",'''

if "tpl-loitering" not in matrix_content:
    matrix_content = matrix_content.replace(OLD_VITRINE, NEW_VITRINE)
    matrix_script.write_text(matrix_content, encoding="utf-8")
    print("Added vitrine template→script mappings to matrix generator")
else:
    print("Matrix generator already has vitrine mappings")

# Verify syntax
import subprocess
r = subprocess.run(["python3", "-m", "py_compile", str(matrix_script)], capture_output=True, text=True)
print("Matrix syntax:", "OK" if r.returncode == 0 else r.stderr)
