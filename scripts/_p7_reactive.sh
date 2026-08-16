#!/usr/bin/env bash
# Hyper-reactive 7-rule Frigate focus validation.
set -uo pipefail
cd ~/citevision-v2 2>/dev/null || cd /mnt/c/Users/gheno/citevision-v2

export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
export BACKEND_API_URL="${BACKEND_API_URL:-http://127.0.0.1:8081}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
export DEMO_MODE=1
export DEMO_EVIDENCE_BACKEND=strict_frigate
export RULE_PREFLIGHT_STRICT=0
export INTERNAL_API_KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
export AI_ENGINE_URL="${AI_ENGINE_URL:-http://127.0.0.1:8001}"
export RULE_TIMEOUT_SEC="${RULE_TIMEOUT_SEC:-600}"
export EVIDENCE_WAIT_SEC="${EVIDENCE_WAIT_SEC:-240}"
export POLL_SEC="${POLL_SEC:-2}"
export DISABLE_END=1
export FRIGATE_EVIDENCE_STRICT=1
export FRIGATE_SPEED_EMIT_MODE=max_in_zone
export FRIGATE_SKIP_PREFLIGHT_REBUILD=1
export FRIGATE_PLATE_LOCAL=1
export REPORT_PATH=/tmp/demo_1hit_seven_reactive.json
LOG=/tmp/demo_1hit_seven_reactive.log

pkill -f 'watch-infra-ports' 2>/dev/null || true
pkill -f 'watch-business-readiness' 2>/dev/null || true

# Sync critical scripts from Windows mount
python3 - <<'PY'
from pathlib import Path
base = Path("/mnt/c/Users/gheno/citevision-v2")
dst_root = Path.home() / "citevision-v2"
if not base.is_dir():
    raise SystemExit(0)
pairs = [
    "scripts/validate_demo_1hit_seven_reactive.py",
    "scripts/validate_demo_1hit_frigate_p3.py",
    "scripts/lib/frigate_detect_gate.py",
    "scripts/lib/env-utils.sh",
    "ai-engine/src/citevision_ai/config.py",
    "ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py",
    "ai-engine/src/citevision_ai/frigate_bridge/bridge.py",
]
for rel in pairs:
    src = base / rel
    if not src.is_file():
        continue
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if dst.resolve() != src.resolve():
        dst.write_bytes(data)
    print("synced", rel)
PY

ROOT="$(pwd)"
# Apply demo reactive env
if [[ -f "$ROOT/scripts/lib/env-utils.sh" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/scripts/lib/env-utils.sh"
  ensure_demo_validation_env "$ROOT" "$ROOT/.env" || true
fi

if [[ "${SKIP_AI_RESTART:-0}" != "1" ]] && [[ -x "$ROOT/scripts/restart-ai-engine.sh" ]]; then
  echo "[p7] restart AI with strict+max_in_zone"
  bash "$ROOT/scripts/restart-ai-engine.sh" || true
elif [[ "${SKIP_AI_RESTART:-0}" == "1" ]]; then
  echo "[p7] SKIP_AI_RESTART=1 — keep current AI process"
fi

bash "$ROOT/scripts/seed-demo-spatial.sh" 2>/dev/null || true
curl -sf -X POST -H "X-Internal-Key: ${INTERNAL_API_KEY}" \
  http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial >/dev/null || true

# One full Frigate reload so demo LPR/zones from (disabled) rules are live.
# Skip when already applied this session (SKIP_FRIGATE_ONESHOT=1) — rebuild cools detector.
if [[ "${SKIP_FRIGATE_ONESHOT:-0}" != "1" ]]; then
  echo "[p7] one-shot Frigate rebuild (apply demo LPR/zones caps)"
  curl -sf --max-time 90 -X POST -H "X-Internal-Key: ${INTERNAL_API_KEY}" \
    http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild \
    && echo " frigate_rebuild_ok" || echo " frigate_rebuild_warn"
  for _ in $(seq 1 30); do
    if curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null; then
      break
    fi
    sleep 2
  done
else
  echo "[p7] SKIP_FRIGATE_ONESHOT=1 — keep live Frigate config"
fi

PY=python3
if [[ -x "$ROOT/ai-engine/.venv/bin/python3" ]]; then
  PY="$ROOT/ai-engine/.venv/bin/python3"
fi
# Ensure paho for detect gate
"$PY" -c "import paho.mqtt.client" 2>/dev/null || "$PY" -m pip install -q paho-mqtt || true

# Clear retained detect ghosts
"$PY" - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "citevision-v2" / "scripts" / "lib"))
try:
    import frigate_detect_gate as g
    cams = g.list_frigate_cameras()
    print(g.clear_retained_detect(cams))
except Exception as e:
    print("gate:", e)
PY

echo "=== p7 reactive start $(date -Is) ===" | tee "$LOG"
"$PY" -u scripts/validate_demo_1hit_seven_reactive.py 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
echo "=== p7 reactive end $(date -Is) rc=$rc ===" | tee -a "$LOG"
exit "$rc"
