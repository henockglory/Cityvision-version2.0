#!/usr/bin/env bash
# Vérifie briques règles composables + honesty redirects (plus d'event live vehicle_corridor)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "=== verify-rules-composition ==="

grep -q trigger_rule "$ROOT/rules-engine/internal/actions/executor.go" || { echo "FAIL: trigger_rule"; exit 1; }
echo "PASS trigger_rule action"

grep -q PublishRuleTrigger "$ROOT/rules-engine/internal/mqttpub/publisher.go" || { echo "FAIL: PublishRuleTrigger"; exit 1; }
echo "PASS mqtt trigger topic"

grep -q SuppressLower "$ROOT/rules-engine/internal/evaluator/engine.go" || { echo "FAIL: suppress_lower"; exit 1; }
echo "PASS suppress_lower model"

# vehicle_corridor must be drop-on-publish (not a live product event)
grep -q 'if et == "vehicle_corridor"' "$ROOT/ai-engine/src/citevision_ai/pipeline.py" || {
  echo "FAIL: vehicle_corridor drop publish missing"
  exit 1
}
echo "PASS vehicle_corridor drop publish"

grep -q 'tpl-wrong-way' "$ROOT/shared/rule-catalog/road-enforcement.json" || {
  echo "FAIL: tpl-wrong-way missing from road-enforcement catalog"
  exit 1
}
echo "PASS tpl-wrong-way catalog"

grep -q 'redirect_to": "tpl-speeding-premium"' "$ROOT/shared/rule-catalog/road-enforcement.json" || {
  echo "FAIL: tpl-traffic-pipeline redirect → tpl-speeding-premium"
  exit 1
}
echo "PASS tpl-traffic-pipeline redirect"

grep -q capability_profiles "$ROOT/backend/internal/ingest/orchestrator.go" || { echo "FAIL: capability_profiles"; exit 1; }
echo "PASS capability_profiles sync"

test -f "$ROOT/shared/rule-catalog/road-enforcement.json" || { echo "FAIL: road-enforcement.json"; exit 1; }
echo "PASS road-enforcement catalog"

grep -q SEQUENCE "$ROOT/frontend/src/components/rules/ConditionTreeEditor.tsx" || { echo "FAIL: SEQUENCE UI"; exit 1; }
echo "PASS SEQUENCE in ConditionTreeEditor"

echo "=== verify-rules-composition OK ==="
