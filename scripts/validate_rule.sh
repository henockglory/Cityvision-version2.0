#!/usr/bin/env bash
# CitéVision Sprint 2 — validate_rule (DoD infalsifiable, Décision 3 / R.3).
#
# Usage:
#   bash scripts/validate_rule.sh <alias>
#   bash scripts/validate_rule.sh speeding
#   bash scripts/validate_rule.sh red_light
#   bash scripts/validate_rule.sh phone
#   bash scripts/validate_rule.sh seatbelt
#   bash scripts/validate_rule.sh counting
#
# Env:
#   VALIDATE_MODE=wait|audit   (default wait — runs 1-hit then DoD; audit = latest only)
#   SKIP_1HIT=1                skip live 1-hit, audit latest alert only
#   SKIP_UI_CAPTURE=1          skip Playwright screenshot
#   UI_URL=http://127.0.0.1:5174
#   RULE_DURATION_SEC=600
#
# Artefacts: validation-evidence/<alias>/<timestamp>/{report.json,report.md,ui.png}
# A global 5/5 claim requires FIVE recent PASS artefacts (one per alias) — never verbal.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ALIAS="${1:-}"
if [[ -z "$ALIAS" ]]; then
  echo "Usage: bash scripts/validate_rule.sh <speeding|red_light|phone|seatbelt|counting>"
  exit 2
fi

# Phase A Tâche 8: refuse Windows mount as runtime (source of truth = ~/citevision-v2).
if [[ "$ROOT" == /mnt/c/* ]] || [[ "$ROOT" == /mnt/d/* ]]; then
  echo "[FAIL] validate_rule refuse ROOT under /mnt/* (got $ROOT)."
  echo "       Open/run from native WSL: ~/citevision-v2 (see OPEN-IN-WSL.txt)."
  exit 1
fi

cd "$ROOT"

if [[ -x "$ROOT/scripts/health_check_all.sh" ]]; then
  echo "=== preflight health_check_all ==="
  bash "$ROOT/scripts/health_check_all.sh" || {
    echo "[FAIL] health_check_all RED — fix infra before validation (R.1)"
    exit 1
  }
fi

export PYTHONPATH="${PYTHONPATH:-}"
exec python3 "$ROOT/scripts/validate_rule_dod.py" --alias "$ALIAS"
