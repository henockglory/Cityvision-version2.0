#!/usr/bin/env bash
# Canonical feu PASS: preflight → 1-hit isolated → DoD validate_rule (light preflight).
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"
LOG="$ROOT/logs/dod-feu-pass-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== dod-feu-pass start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

bash "$ROOT/scripts/_start_dockerd_wsl.sh" 2>/dev/null || true
bash "$ROOT/scripts/health_check_all.sh" || {
  echo "[FAIL] health_check_all RED"
  exit 1
}

bash "$ROOT/scripts/_restart_ai_cuda.sh"
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:8001/health >/dev/null && break
  sleep 3
done
curl -sf http://127.0.0.1:8001/health >/dev/null || { echo "[FAIL] AI not up"; exit 2; }

bash "$ROOT/scripts/ensure-demo-streams.sh" || true
bash "$ROOT/scripts/microtest/_wait_frigate_stable.sh" || true

if ! curl -sf -o /dev/null http://127.0.0.1:5174/; then
  (cd "$ROOT/frontend" && nohup npm run dev -- --host 127.0.0.1 --port 5174 >> "$ROOT/logs/vite-dod.log" 2>&1 &)
  for i in $(seq 1 30); do
    curl -sf -o /dev/null http://127.0.0.1:5174/ && break
    sleep 2
  done
fi

bash "$ROOT/scripts/microtest/_sync_1hit_feu_to_wsl.sh"
bash "$ROOT/scripts/microtest/_preflight_feu_gate.sh"

export FEU_1HIT_REQUIRE_COMPLETE="${FEU_1HIT_REQUIRE_COMPLETE:-0}"
bash "$ROOT/scripts/microtest/_run_1hit_feu_isolated.sh"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] 1-hit isolated exit=$RC"
  exit "$RC"
fi

VALIDATE_LOG="$(ls -t "$ROOT"/logs/validate-feu-*.log 2>/dev/null | head -1)"
if ! grep -q '^RESULT: PASS' "$VALIDATE_LOG" 2>/dev/null; then
  echo "[FAIL] microtest validate log missing RESULT: PASS ($VALIDATE_LOG)"
  exit 3
fi

export PREFLIGHT_VALIDATE_LIGHT=1
export SKIP_1HIT=1
bash "$ROOT/scripts/validate_rule.sh" red_light
DOD_RC=$?
echo "=== dod-feu-pass done exit=$DOD_RC log=$LOG ==="
exit "$DOD_RC"
