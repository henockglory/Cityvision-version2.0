#!/usr/bin/env bash
# Sync Demo5 campaign files Windows → WSL citevision-v2
set -euo pipefail
WIN="/mnt/c/Users/gheno/citevision"
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
for f in \
  scripts/microtest/_microtest_demo_5rules_1hit.sh \
  scripts/microtest/_microtest_demo5_preflight.sh \
  scripts/microtest/_demo5_live_line.sh \
  scripts/microtest/_demo5_export_evidence_html.py \
  scripts/microtest/_microtest_common.sh \
  scripts/microtest/_run_demo5_campaign_wsl.sh \
  scripts/microtest/_sync_demo5_to_wsl.sh \
  scripts/_validate_rule_frigate_1hit.py \
  scripts/_observe_1hit_blockers.py \
  scripts/patch-demo-speed-zone.sh \
  ai-engine/src/citevision_ai/vlm/gemini_client.py \
  ai-engine/src/citevision_ai/vlm/queue.py \
  ai-engine/src/citevision_ai/frigate_bridge/bridge.py \
  ai-engine/src/citevision_ai/frigate_bridge/snapshot.py \
  ai-engine/tests/test_gemini_vlm.py; do
  mkdir -p "$ROOT/$(dirname "$f")"
  cp "$WIN/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
done
chmod +x "$ROOT/scripts/microtest/"*.sh 2>/dev/null || true
echo "synced to $ROOT"
