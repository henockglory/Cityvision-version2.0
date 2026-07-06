#!/usr/bin/env bash
# Full charter re-audit: stack check → validate 5 rules → audit JSON → roadmap.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export ADMIN_EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD required}"
export REPORT_TAG=final
export SPEED_DEFERRED=0
export ALERT_WAIT_SEC="${ALERT_WAIT_SEC:-120}"
export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export DEMO_SETTLE_SEC="${DEMO_SETTLE_SEC:-45}"

echo "=== Health gate ==="
curl -sf "http://127.0.0.1:8081/health" >/dev/null
curl -sf "http://127.0.0.1:8001/health" >/dev/null
curl -sf "http://127.0.0.1:8010/health" >/dev/null

echo "=== [N.116] validate_demo 5 rules ==="
python3 scripts/validate_demo_five_rules.py

echo "=== Charter audit + roadmap ==="
python3 scripts/audit-charter-138.py
python3 scripts/generate-roadmap-138-status.py
python3 scripts/_list_audit_gaps.py

echo "Done. See logs/demo-five-rules-final-report.json and docs/CHARTER-138-AUDIT.json"
