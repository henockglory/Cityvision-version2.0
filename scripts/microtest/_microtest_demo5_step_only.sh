#!/usr/bin/env bash
# Relance une seule étape Demo5 (ex: ceinture) après preflight léger.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
STEP="${1:-4}"
WIN="/mnt/c/Users/gheno/citevision"
cd "$ROOT"
for f in scripts/microtest/_microtest_demo5_preflight.sh \
  scripts/microtest/_microtest_demo_5rules_1hit.sh \
  scripts/microtest/_microtest_common.sh \
  scripts/_validate_rule_frigate_1hit.py; do
  cp "$WIN/$f" "$ROOT/$f" 2>/dev/null || true
  sed -i 's/\r$//' "$ROOT/$f" 2>/dev/null || true
done
export MICROTEST_AUTO_YES=1 DEMO5_STEP_RETRY=1 CEINTURE_PIPELINE_OR_ALERT=1 DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
if [ "${DEMO5_SKIP_PREFLIGHT:-0}" != "1" ]; then
  bash "$ROOT/scripts/microtest/_microtest_demo5_preflight.sh" "$ROOT/logs/demo5-step-preflight.log"
else
  curl -sf -m 8 http://127.0.0.1:8081/health >/dev/null \
    || bash "$ROOT/scripts/_restart_backend.sh"
  curl -sf -m 8 http://127.0.0.1:8081/health >/dev/null \
    || { echo "backend still down"; exit 2; }
fi
source "$ROOT/scripts/microtest/_microtest_common.sh"
export RULE_DURATION_SEC=1200 POLL_SEC=12
API="${BACKEND_API_URL:-http://127.0.0.1:8081}"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
case "$STEP" in
  2)
    export RULE_NAME="Démo · Excès de vitesse" RULE_ALIAS=vitesse RULE_DURATION_SEC=600 POLL_SEC=15
    DEMO_SPEED_LIMIT_KMH=1 DEMO_ORG_ID="$DEMO_ORG_ID" bash "$ROOT/scripts/patch-demo-speed-zone.sh" || true
    curl -sf -X POST -H "X-Internal-Key: $KEY" "$API/api/v1/internal/ingest/resync-spatial" || true
    bash "$ROOT/scripts/ensure-demo-streams.sh" || true
    sleep 8
    ;;
  4) export RULE_NAME="Démo · Non-port ceinture" RULE_ALIAS=ceinture RULE_DURATION_SEC=720 POLL_SEC=15 ;;
  *) echo "unsupported step $STEP (use 2 or 4)"; exit 2 ;;
esac
set +e
python3 -u "$ROOT/scripts/_validate_rule_frigate_1hit.py"
rc=$?
echo "STEP_ONLY_DONE step=$STEP rc=$rc"
exit "$rc"
