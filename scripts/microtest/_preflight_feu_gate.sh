#!/usr/bin/env bash
# Phase 1 GO/NO-GO before 1-hit feu — infra chaude + Frigate events + ingest.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"

# shellcheck source=scripts/microtest/_microtest_common.sh
source "$ROOT/scripts/microtest/_microtest_common.sh"

MIN_FRIGATE_CAR_EVENTS="${FEU_PREFLIGHT_MIN_CAR_EVENTS:-3}"
MIN_INGEST_FRAMES="${FEU_PREFLIGHT_MIN_INGEST_FRAMES:-100}"
FRIGATE_WINDOW_SEC="${FEU_FRIGATE_WINDOW_SEC:-120}"
MAX_WARM_SEC="${FEU_PREFLIGHT_WARM_SEC:-180}"

echo "=== preflight feu gate (min_car=${MIN_FRIGATE_CAR_EVENTS} ingest>=${MIN_INGEST_FRAMES}) ==="

if ! bash "$ROOT/scripts/health_check_all.sh" > "$ROOT/logs/preflight-feu-gate-health.log" 2>&1; then
  echo "[NO-GO] health_check_all FAIL — see logs/preflight-feu-gate-health.log"
  exit 2
fi
if grep -qE 'summary FAIL=[1-9]' "$ROOT/logs/preflight-feu-gate-health.log" 2>/dev/null; then
  echo "[NO-GO] health_check_all has FAIL>0"
  exit 2
fi

curl -sf -m 5 "http://127.0.0.1:8081/health" >/dev/null || {
  echo "[NO-GO] backend :8081 down"
  exit 2
}
curl -sf -m 5 "http://127.0.0.1:8010/health" >/dev/null || {
  echo "[NO-GO] rules-engine :8010 down"
  exit 2
}

echo "=== warm feu camera (max ${MAX_WARM_SEC}s) ==="
WARM_LINE="$(microtest_warm_feu_camera "$MAX_WARM_SEC" 2>&1 | tail -1 || true)"
echo "$WARM_LINE"
if ! grep -q '^cam_id=' <<<"$WARM_LINE"; then
  echo "[NO-GO] feu camera warm failed"
  bash "$ROOT/scripts/ensure-demo-streams.sh" || true
  sleep 30
  WARM_LINE="$(microtest_warm_feu_camera "$MAX_WARM_SEC" 2>&1 | tail -1 || true)"
  echo "retry: $WARM_LINE"
  if ! grep -q '^cam_id=' <<<"$WARM_LINE"; then
    exit 2
  fi
fi

CAM_ID="$(echo "$WARM_LINE" | sed -n 's/^cam_id=\([^ ]*\).*/\1/p')"
export FEU_CAMERA_ID="$CAM_ID"
FRIGATE_CAM="cv_${CAM_ID}"

echo "=== wait ingest >= ${MIN_INGEST_FRAMES} (max ${MAX_WARM_SEC}s) ==="
DEADLINE=$(( $(date +%s) + MAX_WARM_SEC ))
FRAMES="${FRAMES:-0}"
while [ "$FRAMES" -lt "$MIN_INGEST_FRAMES" ] && [ "$(date +%s)" -lt "$DEADLINE" ]; do
  FRAMES="$(curl -sf -m 8 "http://127.0.0.1:8001/cameras" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for c in d.get('cameras',[]):
    if c.get('camera_id')=='${CAM_ID}':
        print(int(c.get('frames_processed') or 0)); break
else:
    print(0)
" 2>/dev/null || echo 0)"
  echo "  ingest frames=${FRAMES}/${MIN_INGEST_FRAMES}"
  if [ "$FRAMES" -ge "$MIN_INGEST_FRAMES" ]; then
    break
  fi
  sleep 10
done
if [ "$FRAMES" -lt "$MIN_INGEST_FRAMES" ]; then
  echo "[NO-GO] ingest frames=${FRAMES} need>=${MIN_INGEST_FRAMES}"
  exit 2
fi
echo "[OK] ingest frames=${FRAMES}"

export FRIGATE_CAM
python3 - <<PY
import json, os, sys, time, urllib.parse, urllib.request

frigate_cam = os.environ["FRIGATE_CAM"]
min_car = int(os.environ.get("FEU_PREFLIGHT_MIN_CAR_EVENTS", "3"))
wait_sec = int(os.environ.get("FEU_FRIGATE_CAR_WAIT_SEC", "120"))
base = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
deadline = time.time() + wait_sec
while time.time() < deadline:
    qs = urllib.parse.urlencode({"camera": frigate_cam, "limit": 50})
    url = f"{base}/api/events?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            events = json.loads(resp.read().decode())
    except Exception as exc:
        print(f"  frigate poll err={exc}", file=sys.stderr)
        time.sleep(8)
        continue
    cars = [ev for ev in events if isinstance(ev, dict) and str(ev.get("label") or "").lower() == "car"]
    print(f"frigate_car_events={len(cars)} cam={frigate_cam[:24]}")
    if len(cars) >= min_car:
        print("[OK] frigate car events warm")
        raise SystemExit(0)
    time.sleep(8)
print(f"[NO-GO] need>={min_car} car events after {wait_sec}s", file=sys.stderr)
sys.exit(2)
PY

echo "=== smoke feu evidence (phase 2) ==="
bash "$ROOT/scripts/microtest/_smoke_feu_evidence.sh"

echo "[GO] preflight feu gate passed cam=${CAM_ID:0:8} frames=${FRAMES}"
