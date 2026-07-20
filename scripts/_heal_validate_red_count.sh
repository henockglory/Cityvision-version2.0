#!/usr/bin/env bash
# Heal Frigate freshness then validate red_light + counting.
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
mkdir -p logs
LOG="$ROOT/logs/heal-validate-red-count.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== START $(date -Is) ==="

# Sync scripts from Windows edit tree
for f in \
  scripts/validate_rule.sh \
  scripts/validate_rule_dod.py \
  scripts/_validate_rule_frigate_1hit.py \
  scripts/capture_alerts_ui.mjs \
  scripts/_heal_for_validate.sh
do
  cp -f "$WIN/$f" "$ROOT/$f" 2>/dev/null || true
  sed -i 's/\r$//' "$ROOT/$f" 2>/dev/null || true
done

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== VIDEOS_PATH ==="
grep -E '^VIDEOS_PATH=' .env || true
ls -la "${VIDEOS_PATH:-/home/gheno/citevision-v2/data/videos}" 2>/dev/null | head -15 || true

echo "=== repair-streams ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || echo repair_fail
echo

echo "=== restart go2rtc + frigate ==="
cd infra
docker compose --env-file "$ROOT/.env" restart go2rtc || true
sleep 3
docker compose --env-file "$ROOT/.env" restart frigate || true
cd "$ROOT"

echo "=== wait frigate API ==="
for i in $(seq 1 60); do
  if timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
    echo "frigate up: $(curl -sf http://127.0.0.1:5000/api/version)"
    break
  fi
  sleep 2
done

echo "=== repair-streams again + resync ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
echo
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial || true
echo

echo "=== wait fresh frigate events (max ~120s) ==="
python3 - <<'PY'
import json, time, urllib.request
url = "http://127.0.0.1:5000/api/events?limit=20"
ok = False
for i in range(40):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read().decode())
        events = data if isinstance(data, list) else data.get("events") or data.get("data") or []
        now = time.time()
        ages = sorted((now - float(e.get("start_time") or 0)) for e in events if e.get("start_time"))
        age0 = ages[0] if ages else 9999
        print(f"  try {i}: n={len(events)} youngest={age0:.0f}s", flush=True)
        if age0 <= 25:
            ok = True
            break
    except Exception as exc:
        print(f"  try {i}: err {exc}", flush=True)
    time.sleep(3)
print("FRESH_OK" if ok else "FRESH_FAIL", flush=True)
raise SystemExit(0 if ok else 1)
PY
FRESH_EC=$?
echo "fresh_ec=$FRESH_EC"

# Ensure OCR + UI still up
curl -sf --max-time 3 http://127.0.0.1:8181/healthz >/dev/null || {
  cd infra
  docker compose --env-file "$ROOT/.env" --profile ocr up -d citevision-ocr || true
  cd "$ROOT"
}
if ! curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null; then
  cd frontend
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  cd "$ROOT"
  sleep 5
fi

bash scripts/health_check_all.sh || true

export RULE_DURATION_SEC=480
export VALIDATE_MODE=wait
export SKIP_FRIGATE_REBUILD=1

echo "########## RED_LIGHT $(date -Is) ##########"
bash scripts/validate_rule.sh red_light
echo EC_red=$?
latest=$(find validation-evidence/red_light -name report.json 2>/dev/null | sort | tail -1)
if [[ -n "${latest:-}" ]]; then
  python3 -c "import json,os;d=json.load(open('$latest'));print('red_light', d.get('result'), 'ui='+str(os.path.exists(os.path.join(os.path.dirname('$latest'),'ui.png'))))"
fi

echo "########## COUNTING $(date -Is) ##########"
bash scripts/validate_rule.sh counting
echo EC_count=$?
latest=$(find validation-evidence/counting -name report.json 2>/dev/null | sort | tail -1)
if [[ -n "${latest:-}" ]]; then
  python3 -c "import json,os;d=json.load(open('$latest'));print('counting', d.get('result'), 'ui='+str(os.path.exists(os.path.join(os.path.dirname('$latest'),'ui.png'))))"
else
  echo counting NO_ARTEFACT
fi

echo "=== FINAL SCORECARD ==="
for a in speeding red_light phone seatbelt counting; do
  latest=$(find validation-evidence/$a -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "${latest:-}" ]]; then
    python3 -c "import json,os;d=json.load(open('$latest'));print(d.get('result'), '$a', 'ui='+str(os.path.exists(os.path.join(os.path.dirname('$latest'),'ui.png'))))"
  else
    echo "NONE $a"
  fi
done
echo "=== DONE $(date -Is) ==="
