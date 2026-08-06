#!/usr/bin/env bash
# Export-only: regenerate the 1-hit feu gallery for an existing run (alert already in DB).
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export HIT1_TS="${HIT1_TS:?HIT1_TS required (e.g. 20260806T101217Z)}"
export HIT1_SINCE="${HIT1_SINCE:?HIT1_SINCE required (e.g. 2026-08-06 10:14:36+00)}"
export PYTHONPATH="$ROOT/ai-engine/src:${PYTHONPATH:-}"
PY="$ROOT/ai-engine/.venv/bin/python"
[ -x "$PY" ] || PY=python3
exec "$PY" scripts/microtest/_export_1hit_feu_gallery.py
