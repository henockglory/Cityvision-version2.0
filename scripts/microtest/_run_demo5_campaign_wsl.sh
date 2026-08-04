#!/usr/bin/env bash
# Wrapper WSL — sync scripts Windows → citevision-v2 puis lance campagne Demo5.
set -euo pipefail
WIN="/mnt/c/Users/gheno/citevision"
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
mkdir -p scripts/microtest logs
for f in \
  scripts/microtest/_microtest_demo_5rules_1hit.sh \
  scripts/microtest/_microtest_demo5_preflight.sh \
  scripts/microtest/_demo5_live_line.sh \
  scripts/microtest/_demo5_export_evidence_html.py \
  scripts/microtest/_microtest_common.sh \
  scripts/_validate_rule_frigate_1hit.py \
  scripts/_observe_1hit_blockers.py \
  scripts/patch-demo-speed-zone.sh; do
  cp "$WIN/$f" "$ROOT/$f" 2>/dev/null || true
  sed -i 's/\r$//' "$ROOT/$f" 2>/dev/null || true
done
for f in \
  ai-engine/src/citevision_ai/vlm/gemini_client.py \
  ai-engine/src/citevision_ai/vlm/queue.py \
  ai-engine/src/citevision_ai/frigate_bridge/bridge.py \
  ai-engine/src/citevision_ai/frigate_bridge/snapshot.py \
  ai-engine/tests/test_gemini_vlm.py; do
  mkdir -p "$ROOT/$(dirname "$f")"
  cp "$WIN/$f" "$ROOT/$f" 2>/dev/null || true
  sed -i 's/\r$//' "$ROOT/$f" 2>/dev/null || true
done
chmod +x "$ROOT/scripts/microtest/"*.sh 2>/dev/null || true
export MICROTEST_AUTO_YES=1
export DEMO5_STEP_RETRY=1
export CEINTURE_PIPELINE_OR_ALERT=1
exec bash "$ROOT/scripts/microtest/_microtest_demo_5rules_1hit.sh"
