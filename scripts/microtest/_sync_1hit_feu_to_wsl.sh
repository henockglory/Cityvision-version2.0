#!/usr/bin/env bash
# Sync fichiers test 1-hit feu isolé Windows → WSL citevision-v2
set -euo pipefail
WIN="/mnt/c/Users/gheno/citevision"
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
for f in \
  scripts/microtest/_run_1hit_feu_isolated.sh \
  scripts/microtest/_preflight_feu_gate.sh \
  scripts/microtest/_smoke_feu_evidence.sh \
  scripts/microtest/_smoke_feu_evidence.py \
  scripts/microtest/_run_validate_feu_once.sh \
  scripts/microtest/_export_1hit_feu_gallery.py \
  scripts/microtest/_microtest_common.sh \
  scripts/_validate_feux_frigate_1hit.py \
  scripts/validate_rule_dod.py \
  scripts/validate_rule.sh \
  scripts/_observe_1hit_blockers.py \
  scripts/preflight-validate.sh \
  scripts/ensure-demo-validation-env.sh \
  scripts/_start_ai.sh \
  scripts/lib/env-utils.sh \
  scripts/lib/cuda-utils.sh \
  ai-engine/src/citevision_ai/config.py \
  ai-engine/src/citevision_ai/pipeline.py \
  ai-engine/src/citevision_ai/road_enforcement/traffic_light.py \
  ai-engine/src/citevision_ai/frigate_bridge/snapshot.py \
  ai-engine/src/citevision_ai/frigate_bridge/bridge.py \
  ai-engine/src/citevision_ai/road_enforcement/red_light_vote.py \
  ai-engine/src/citevision_ai/frigate_bridge/snapshot.py \
  ai-engine/src/citevision_ai/vlm/gemini_client.py \
  ai-engine/src/citevision_ai/vlm/queue.py \
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  ai-engine/tests/test_evidence_abort_stats.py \
  ai-engine/tests/test_frigate_bridge.py \
  ai-engine/tests/test_frigate_backend.py; do
  mkdir -p "$ROOT/$(dirname "$f")"
  cp "$WIN/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
done
chmod +x "$ROOT/scripts/microtest/"*.sh 2>/dev/null || true
echo "synced 1hit-feu files to $ROOT"
