#!/usr/bin/env bash
# Canonical Phase 3 + DoD — heal stack, preflight, 1-hit, validate_rule.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"

echo "=== sync ==="
bash "$ROOT/scripts/microtest/_sync_1hit_feu_to_wsl.sh"

echo "=== heal docker + services ==="
bash "$ROOT/scripts/_start_dockerd_wsl.sh" 2>/dev/null || true
bash "$ROOT/scripts/ensure-demo-streams.sh" 2>/dev/null || true
bash "$ROOT/scripts/_restart_backend.sh" 2>/dev/null || true
bash "$ROOT/scripts/_start-rules-engine.sh" 2>/dev/null || true
bash "$ROOT/scripts/_restart_ai_cuda.sh" 2>/dev/null || true

echo "=== wait AI ==="
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "AI up attempt=$i"
    break
  fi
  sleep 3
done
curl -sf http://127.0.0.1:8001/health >/dev/null || { echo "[FAIL] AI not up"; exit 2; }

echo "=== wait Frigate stable ==="
bash "$ROOT/scripts/microtest/_wait_frigate_stable.sh" 2>/dev/null || {
  docker restart citevision-v2-frigate 2>/dev/null || true
  sleep 15
  bash "$ROOT/scripts/microtest/_wait_frigate_stable.sh"
}

echo "=== start Vite (DoD UI) ==="
if ! curl -sf -o /dev/null http://127.0.0.1:5174/ 2>/dev/null; then
  pkill -f 'vite.*5174' 2>/dev/null || true
  (cd "$ROOT/frontend" && nohup npm run dev -- --host 127.0.0.1 --port 5174 >> "$ROOT/logs/vite-dod.log" 2>&1 &)
  for i in $(seq 1 30); do
    curl -sf -o /dev/null http://127.0.0.1:5174/ && break
    sleep 2
  done
fi
curl -sf -o /dev/null http://127.0.0.1:5174/ && echo "Vite OK" || echo "[WARN] Vite down — DoD may be PARTIAL"

echo "=== health_check ==="
bash "$ROOT/scripts/health_check_all.sh"

echo "=== preflight feu gate ==="
bash "$ROOT/scripts/microtest/_preflight_feu_gate.sh"

echo "=== Phase 3: 1-hit isolated ==="
export PREFLIGHT_VALIDATE_LIGHT=1
export FEU_SKIP_FRIGATE_REBUILD=1
bash "$ROOT/scripts/microtest/_run_1hit_feu_isolated.sh"

echo "=== DoD validate_rule ==="
export PREFLIGHT_VALIDATE_LIGHT=1
export SKIP_1HIT=1
bash "$ROOT/scripts/validate_rule.sh" red_light
