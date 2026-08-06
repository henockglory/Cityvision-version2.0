#!/usr/bin/env bash
# Phase 2 — smoke evidence/request on latest Frigate car event (feu cam).
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"
export PYTHONPATH="${ROOT}/ai-engine/src:${PYTHONPATH:-}"
exec python3 "$ROOT/scripts/microtest/_smoke_feu_evidence.py"
