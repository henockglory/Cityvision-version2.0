#Requires -Version 5.1
<#
.SYNOPSIS
  Démarre TOUTE la stack CitéVision (infra Docker + vidéos démo + Frigate + API + IA + rules + UI).
.NOTES
  Runtime = WSL ~/citevision-v2. Double-cliquer ou :
    powershell -ExecutionPolicy Bypass -File ops\Start-CiteVision.ps1
  Quitte 0 seulement si la gate santé finale est verte (prêt tests 1-à-1).
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
$WslRoot = "/home/gheno/citevision-v2"

$bash = @'
#!/usr/bin/env bash
set -uo pipefail
export PATH="/usr/local/go/bin:/home/gheno/go/bin:${PATH:-}"
ROOT="${CV_ROOT:-/home/gheno/citevision-v2}"
cd "$ROOT" || { echo "[FAIL] ROOT=$ROOT introuvable"; exit 1; }
if [[ "$ROOT" == /mnt/c/* ]] || [[ "$ROOT" == /mnt/d/* ]]; then
  echo "[FAIL] Interdit de démarrer depuis /mnt/* — utilise $HOME/citevision-v2"
  exit 1
fi

source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR" "$ROOT/backend/bin"

retry() {
  local n="$1"; shift
  local i=1
  until "$@"; do
    if (( i >= n )); then return 1; fi
    echo "[RETRY $i/$n] $*"
    sleep $((i * 2))
    i=$((i + 1))
  done
}

wait_url() {
  local url="$1" secs="${2:-90}"
  local i=0
  while (( i < secs )); do
    curl -sf --max-time 3 "$url" >/dev/null 2>&1 && return 0
    sleep 2
    i=$((i + 2))
  done
  return 1
}

echo "╔══════════════════════════════════════════════╗"
echo "║  CitéVision — START ALL ($(date -Is))        ║"
echo "╚══════════════════════════════════════════════╝"
echo "ROOT=$ROOT"

# --- 0. env vidéo démo ---
VIDEOS_DEFAULT="$ROOT/data/videos"
mkdir -p "$VIDEOS_DEFAULT"
if grep -q '^VIDEOS_PATH=' "$ENV_FILE" 2>/dev/null; then
  sed -i "s|^VIDEOS_PATH=.*|VIDEOS_PATH=$VIDEOS_DEFAULT|" "$ENV_FILE"
else
  echo "VIDEOS_PATH=$VIDEOS_DEFAULT" >> "$ENV_FILE"
fi
# Ports / flags utiles démo
grep -q '^DEMO_MODE=' "$ENV_FILE" || echo 'DEMO_MODE=1' >> "$ENV_FILE"
grep -q '^ALERT_EMAIL_TO=' "$ENV_FILE" || echo 'ALERT_EMAIL_TO=demo@citevision.local' >> "$ENV_FILE"
load_dotenv "$ENV_FILE"

# --- 1. dockerd ---
echo "=== [1/9] dockerd ==="
bash "$ROOT/scripts/_start_dockerd_wsl.sh" 2>/dev/null || true
retry 30 docker info >/dev/null 2>&1 || { echo "[FAIL] dockerd"; exit 1; }
echo "[OK] dockerd"

# --- 2. infra docker (vidéos via go2rtc mount) ---
echo "=== [2/9] docker compose infra + frigate + ocr ==="
cd "$ROOT/infra"
docker compose --env-file "$ENV_FILE" up -d \
  postgres redis mosquitto minio go2rtc mailhog ocr frigate 2>&1 | tail -20
cd "$ROOT"

retry 45 docker exec citevision-v2-postgres pg_isready -U citevision >/dev/null 2>&1 \
  || { echo "[FAIL] postgres"; exit 1; }
retry 30 curl -sf --max-time 3 http://127.0.0.1:1984/api >/dev/null \
  || { echo "[FAIL] go2rtc"; exit 1; }
echo "[OK] postgres + go2rtc"

# Vérifier montage vidéos
if ! docker exec citevision-v2-go2rtc ls /videos >/dev/null 2>&1; then
  echo "[WARN] /videos absent dans go2rtc — recreate go2rtc"
  docker rm -f citevision-v2-go2rtc 2>/dev/null || true
  (cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" up -d go2rtc)
  sleep 3
fi
echo "[INFO] démo videos sample:"
docker exec citevision-v2-go2rtc sh -c 'ls /videos/demo 2>/dev/null | head -5' || true

# --- 3. backend ---
echo "=== [3/9] backend API :8081 ==="
export RULE_CATALOG_PATH="${RULE_CATALOG_PATH:-$ROOT/shared/rule-catalog}"
export SHARED_PATH="${SHARED_PATH:-$ROOT/shared}"
if [[ ! -x "$ROOT/backend/bin/citevision-api" ]]; then
  (cd "$ROOT/backend" && go build -o bin/citevision-api ./cmd/api) || { echo "[FAIL] go build api"; exit 1; }
fi
python3 "$ROOT/scripts/_restart_backend.py" || true
wait_url "http://127.0.0.1:8081/health" 90 || {
  echo "[FAIL] backend health"; tail -40 "$LOGDIR/backend.log" 2>/dev/null || true; exit 1
}
echo "[OK] backend"

# --- 4. AI ---
echo "=== [4/9] AI engine :8001 (GPU) ==="
python3 "$ROOT/scripts/_restart_ai.py" || true
wait_url "http://127.0.0.1:8001/health" 180 || {
  echo "[FAIL] AI health"; tail -40 "$LOGDIR/ai-engine.log" 2>/dev/null || true; exit 1
}
# GPU gate
python3 - <<'PY' || { echo "[FAIL] GPU / models"; exit 1; }
import json, urllib.request, sys
d=json.load(urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=10))
ok = str(d.get("gpu_active","")).lower() in ("1","true","yes") and str(d.get("yolo_loaded","")).lower() in ("1","true","yes")
print("gpu_active=", d.get("gpu_active"), "yolo=", d.get("yolo_loaded"), "plate=", d.get("plate_loaded"))
sys.exit(0 if ok else 1)
PY
echo "[OK] AI GPU"

# --- 5. rules-engine ---
echo "=== [5/9] rules-engine :8010 ==="
bash "$ROOT/scripts/_start-rules-engine.sh" 2>&1 | tail -20
wait_url "http://127.0.0.1:8010/health" 60 || { echo "[FAIL] rules-engine"; exit 1; }
echo "[OK] rules-engine"

# --- 6. streams démo + Frigate ---
echo "=== [6/9] repair-streams + Frigate heal ==="
for i in 1 2 3; do
  curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/demo/repair-streams" \
    -H "X-Internal-Key: $KEY" && break
  sleep 3
done
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: $KEY" || true
# Frigate up
if ! wait_url "http://127.0.0.1:5000/api/version" 90; then
  echo "[WARN] Frigate down — compose recreate"
  (cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" up -d frigate)
  wait_url "http://127.0.0.1:5000/api/version" 120 || { echo "[FAIL] Frigate"; exit 1; }
fi
# Soft heal si events vides
bash "$ROOT/scripts/_heal_frigate_now.sh" 2>&1 | tail -25 || true
echo "[OK] Frigate $(curl -sf http://127.0.0.1:5000/api/version)"

# --- 7. pipeline ingest ---
echo "=== [7/9] demo pipeline (ingest caméras) ==="
bash "$ROOT/scripts/ensure-demo-pipeline.sh" 2>&1 | tail -40
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: $KEY" >/dev/null || true
# attendre ≥1 caméra running
ok_cam=0
for _ in $(seq 1 24); do
  n=$(curl -sf http://127.0.0.1:8001/cameras 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print(sum(1 for x in (d.get('cameras') or []) if x.get('running')))" 2>/dev/null || echo 0)
  if [[ "${n:-0}" -ge 1 ]]; then ok_cam=1; echo "[OK] cameras running=$n"; break; fi
  sleep 5
done
if [[ "$ok_cam" != "1" ]]; then
  echo "[FAIL] aucune caméra IA en ingest — vérifier vidéos + zones"
  exit 1
fi

# --- 8. frontend ---
echo "=== [8/9] frontend Vite :5174 ==="
bash "$ROOT/scripts/ensure-frontend.sh" 2>&1 | tail -20
wait_url "http://127.0.0.1:5174/" 60 || { echo "[FAIL] frontend"; exit 1; }
echo "[OK] frontend"

# --- 9. gate santé ---
echo "=== [9/9] health_check_all ==="
set +e
bash "$ROOT/scripts/health_check_all.sh"
HC=$?
set -e

# Gate stricte services (ignore WARN disque si services OK)
python3 - <<'PY'
import json, urllib.request, sys
checks = [
  ("API", "http://127.0.0.1:8081/health"),
  ("AI", "http://127.0.0.1:8001/health"),
  ("RULES", "http://127.0.0.1:8010/health"),
  ("UI", "http://127.0.0.1:5174/"),
  ("FRIGATE", "http://127.0.0.1:5000/api/version"),
  ("GO2RTC", "http://127.0.0.1:1984/api"),
  ("MAILHOG", "http://127.0.0.1:8025/"),
]
fail=0
for name,url in checks:
  try:
    urllib.request.urlopen(url, timeout=5).read(64)
    print(f"[GATE OK] {name}")
  except Exception as e:
    print(f"[GATE FAIL] {name}: {e}")
    fail=1
sys.exit(fail)
PY
GATE=$?

if [[ "$GATE" != "0" ]]; then
  echo ""
  echo "╔══════════════════════════════════════════════╗"
  echo "║  START FAILED — stack incomplete             ║"
  echo "╚══════════════════════════════════════════════╝"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  CitéVision READY — tests 1-à-1 possibles    ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  UI       http://127.0.0.1:5174              ║"
echo "║  API      http://127.0.0.1:8081              ║"
echo "║  AI       http://127.0.0.1:8001              ║"
echo "║  Rules    http://127.0.0.1:8010              ║"
echo "║  Frigate  http://127.0.0.1:5000              ║"
echo "║  Mailhog  http://127.0.0.1:8025              ║"
echo "║  go2rtc   http://127.0.0.1:1984              ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  health_check_all exit=$HC (0=green)         ║"
echo "║  Règles Démo: active-les UNE à une pour test ║"
echo "╚══════════════════════════════════════════════╝"
exit 0
'@

$tmp = Join-Path $env:TEMP "citevision-start-all.sh"
[System.IO.File]::WriteAllText($tmp, ($bash -replace "`r`n","`n" -replace "`r","`n"))
Get-Content -LiteralPath $tmp -Raw | wsl -d $Distro -- bash -c "cat > /tmp/citevision-start-all.sh && sed -i 's/\r`$//' /tmp/citevision-start-all.sh && chmod +x /tmp/citevision-start-all.sh && CV_ROOT=$WslRoot bash /tmp/citevision-start-all.sh"
exit $LASTEXITCODE
