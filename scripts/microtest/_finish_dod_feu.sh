#!/usr/bin/env bash
# Re-export galerie 1-hit feu après validate PASS + DoD validate_rule.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
export PATH="${ROOT}/ai-engine/.venv/bin:${PATH}"

TS="${1:-20260806T062500Z}"
HIT1_SINCE="${2:-2026-08-06 06:25:43+00}"

export HIT1_TS="$TS"
export OBSERVE_TS="$TS"
export HIT1_SINCE="$HIT1_SINCE"
export FEU_1HIT_STRICT=1

echo "=== ensure Frigate + UI ==="
docker start citevision-v2-frigate 2>/dev/null || true
for i in $(seq 1 20); do
  curl -sf -m 5 http://127.0.0.1:5000/api/version >/dev/null && break
  sleep 3
done
if ! curl -sf -o /dev/null http://127.0.0.1:5174/; then
  pkill -f 'vite.*5174' 2>/dev/null || true
  (cd "$ROOT/frontend" && nohup npm run dev -- --host 127.0.0.1 --port 5174 >> "$ROOT/logs/vite-dod.log" 2>&1 &)
  for i in $(seq 1 25); do
    curl -sf -o /dev/null http://127.0.0.1:5174/ && break
    sleep 2
  done
fi

echo "=== re-export gallery TS=$TS ==="
python3 -u "$ROOT/scripts/microtest/_export_1hit_feu_gallery.py" 2>&1 | tee "$ROOT/logs/export-rerun-${TS}.log"
grep '^OVERALL_PASS=' "$ROOT/logs/export-rerun-${TS}.log" || true

echo "=== DoD validate_rule (SKIP_1HIT) ==="
export PREFLIGHT_VALIDATE_LIGHT=1
export SKIP_1HIT=1
bash "$ROOT/scripts/validate_rule.sh" red_light 2>&1 | tee "$ROOT/logs/validate-rule-red_light-${TS}.log"
