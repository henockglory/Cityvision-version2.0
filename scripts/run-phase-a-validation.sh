#!/usr/bin/env bash
# Lot 1 — Phase A 4/5 validation [N.116–N.122]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

export ADMIN_EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Henockglory@03}"
export VALIDATE_ONLY="${VALIDATE_ONLY:-Démo · Comptage véhicules,Démo · Non-port ceinture,Démo · Téléphone au volant,Démo · Feu rouge}"
export SPEED_DEFERRED=1
export REPORT_TAG=final
export TARGET_DETECTIONS="${TARGET_DETECTIONS:-2}"
export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export DEMO_SETTLE_SEC="${DEMO_SETTLE_SEC:-40}"

echo "=== Phase A validation 4/5 (vitesse deferred) ==="
python3 scripts/validate_demo_five_rules.py

echo "=== Stack health [N.120] ==="
if [[ -x scripts/verify-ai-ingest.sh ]]; then
  scripts/verify-ai-ingest.sh || echo "WARN: verify-ai-ingest non vert"
fi

echo "=== Roadmap tracker ==="
python3 scripts/generate-roadmap-138-status.py

echo "Done: logs/demo-five-rules-final-report.json"
