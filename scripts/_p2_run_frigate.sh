#!/usr/bin/env bash
# Launch protocole 2 Frigate 1-hit runner with sane env.
set -uo pipefail
cd ~/citevision-v2
export ADMIN_PASSWORD='Hologram2026!'
export ADMIN_EMAIL='glory.henock@hologram.cd'
export BACKEND_API_URL='http://127.0.0.1:8081'
export DEMO_ORG_ID='74d51ead-97a7-4e41-a488-503a9b90c466'
export DEMO_MODE=1
export DEMO_EVIDENCE_BACKEND=strict_frigate
export RULE_PREFLIGHT_STRICT=0
export INTERNAL_API_KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
export AI_ENGINE_URL='http://127.0.0.1:8001'
export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-720}"
export POLL_SEC="${POLL_SEC:-10}"
export DISABLE_END=1
export REPORT_PATH=/tmp/demo_1hit_frigate_p2.json
# Skip AI restart on every run unless asked — keeps Frigate bridge warm
export P2_SKIP_GEMINI_RESTART="${P2_SKIP_GEMINI_RESTART:-1}"
# Skip Feu if already PASS in prior partial run
export P2_SKIP_RULES="${P2_SKIP_RULES:-}"
LOG=/tmp/demo_1hit_frigate_p2.log

# Pause flappers that may restart API mid-run
for w in watch-infra-ports watch-business-readiness; do
  pkill -f "$w" 2>/dev/null || true
done
# Keep watch-backend if IPv4-fixed; otherwise pause too during run
if pgrep -af 'watch-backend' | grep -q .; then
  echo "[info] watch-backend still running (should be IPv4-fixed)"
fi

echo "=== start $(date -Is) ===" | tee "$LOG"
PY=python3
if [[ -x "$HOME/citevision-v2/ai-engine/.venv/bin/python3" ]]; then
  PY="$HOME/citevision-v2/ai-engine/.venv/bin/python3"
fi
# Prefer venv so paho-mqtt is available for Frigate detect boost
"$PY" -u scripts/validate_demo_1hit_frigate_p2.py 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
echo "=== end $(date -Is) rc=$rc ===" | tee -a "$LOG"
exit "$rc"
