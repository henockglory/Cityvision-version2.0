#!/usr/bin/env bash
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
TS="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
export HIT1_TS="$TS"
export FEU_1HIT_STRICT=1
export RED_LIGHT_VOTE_MODE=lf_or_g
export RED_LIGHT_GATE_MODE=raw
export RULE_DURATION_SEC=420
export EVIDENCE_SETTLE_SEC=90
export FEU_SKIP_FRIGATE_REBUILD=1
export FEU_MIN_INGEST_FRAMES=100
export DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466
export POLL_SEC=8

curl -sf http://127.0.0.1:8081/health >/dev/null || bash "$ROOT/scripts/_restart_backend.sh"
curl -sf http://127.0.0.1:8010/health >/dev/null || bash "$ROOT/scripts/_start-rules-engine.sh"

python3 -u "$ROOT/scripts/_validate_feux_frigate_1hit.py" 2>&1 | tee "$ROOT/logs/validate-feu-${TS}.log"
grep '^RESULT:' "$ROOT/logs/validate-feu-${TS}.log" || true
export HIT1_SINCE="$(grep '^HIT1_SINCE=' "$ROOT/logs/validate-feu-${TS}.log" | tail -1 | cut -d= -f2-)"
export OBSERVE_TS="$TS"
python3 -u "$ROOT/scripts/microtest/_export_1hit_feu_gallery.py" 2>&1 | tee "$ROOT/logs/export-feu-${TS}.log"
