#!/usr/bin/env bash
set -euo pipefail
WIN="/mnt/c/Users/gheno/citevision"
WSL="$HOME/citevision-v2"
for f in \
  ai-engine/src/citevision_ai/road_enforcement/traffic_light.py \
  ai-engine/src/citevision_ai/road_enforcement/zone_speed.py \
  ai-engine/src/citevision_ai/analytics/zone_speed.py \
  rules-engine/internal/actions/executor.go \
  scripts/validate_demo_five_rules.py \
  scripts/validate-demo-tuning.sh \
  scripts/force-spatial-reload.sh \
  backend/cmd/seed-demo-spatial/main.go; do
  if [[ -f "$WIN/$f" ]]; then
    mkdir -p "$(dirname "$WSL/$f")"
    cp "$WIN/$f" "$WSL/$f"
  fi
done
python3 "$WSL/scripts/fix-crlf.py" \
  "$WSL/scripts/validate-demo-tuning.sh" \
  "$WSL/scripts/force-spatial-reload.sh" 2>/dev/null || true
cd "$WSL"
bash scripts/validate-demo-tuning.sh 2>&1 | tee logs/demo-tuning-run.log
