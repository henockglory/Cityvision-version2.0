#!/usr/bin/env bash
set -euo pipefail
WIN="/mnt/c/Users/gheno/citevision"
WSL="$HOME/citevision-v2"
for f in \
  rules-engine/internal/actions/executor.go \
  rules-engine/internal/mqttpub/publisher.go \
  backend/internal/alerts/service.go \
  scripts/validate_demo_five_rules.py \
  scripts/validate-demo-seatbelt-quick.sh \
  scripts/monitor_traffic_light_states.py; do
  mkdir -p "$(dirname "$WSL/$f")"
  cp "$WIN/$f" "$WSL/$f"
done
python3 "$WSL/scripts/fix-crlf.py" \
  "$WSL/scripts/validate-demo-seatbelt-quick.sh"

cd "$WSL"
echo "========== 1/2 SEATBELT QUICK TEST =========="
bash scripts/validate-demo-seatbelt-quick.sh 2>&1 | tee logs/seatbelt-quick-run.log || SB=$?
SB=${SB:-0}

echo ""
echo "========== 2/2 TRAFFIC LIGHT MQTT (180s) =========="
bash "$WSL/scripts/force-spatial-reload.sh" 2>&1 | tail -5 || true
PY="$WSL/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
"$PY" "$WSL/scripts/monitor_traffic_light_states.py" 180 2>&1 | tee logs/traffic-light-monitor.log
TL=$?

echo ""
echo "========== SUMMARY =========="
echo "seatbelt exit=$SB"
echo "traffic_light exit=$TL"
exit $(( SB != 0 ? SB : TL ))
