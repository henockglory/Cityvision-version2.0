#!/usr/bin/env bash
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"
export HIT1_SINCE='2026-08-06 06:25:43+00'
export OBSERVE_TS='20260806T062500Z'
export HIT1_TS='20260806T062500Z'
export FEU_1HIT_STRICT=1
docker start citevision-v2-frigate 2>/dev/null || true
sleep 8
python3 -u "$ROOT/scripts/microtest/_export_1hit_feu_gallery.py"
