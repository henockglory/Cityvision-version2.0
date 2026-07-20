#Requires -Version 5.1
<#
.SYNOPSIS
  Arrête proprement toute la stack CitéVision (ordre sûr) pour libérer CPU/GPU/RAM/disque.
.NOTES
  powershell -ExecutionPolicy Bypass -File ops\Stop-CiteVision.ps1
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
$WslRoot = "/home/gheno/citevision-v2"

$bash = @'
#!/usr/bin/env bash
set -uo pipefail
ROOT="${CV_ROOT:-/home/gheno/citevision-v2}"
cd "$ROOT" || { echo "[FAIL] ROOT=$ROOT"; exit 1; }
source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true
ENV_FILE="${ROOT}/.env"
KEY="changeme_internal_service_key"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source <(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | sed 's/\r$//'); set +a
  KEY="${INTERNAL_API_KEY:-$KEY}"
fi
LOGDIR="$ROOT/logs"

echo "╔══════════════════════════════════════════════╗"
echo "║  CitéVision — STOP ALL ($(date -Is))         ║"
echo "╚══════════════════════════════════════════════╝"

# 1) Couper règles Démo (anti refill Frigate)
echo "=== [1/6] disable demo rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%';" 2>/dev/null \
  || echo "[WARN] postgres indisponible pour disable rules"

# 2) Watchdogs + process applicatifs
echo "=== [2/6] stop watchdogs / frontend / AI / rules / backend ==="
for svc in watch-demo-stack watch-backend watch-ai-ingest frontend ai-engine rules-engine backend; do
  if [[ -f "$LOGDIR/${svc}.pid" ]]; then
    pid=$(cat "$LOGDIR/${svc}.pid" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]]; then kill "$pid" 2>/dev/null || true; fi
    rm -f "$LOGDIR/${svc}.pid"
  fi
done
pkill -f 'watch-backend|watch-ai-ingest|watch-demo-stack' 2>/dev/null || true
pkill -f 'vite|ensure-frontend' 2>/dev/null || true
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
pkill -f 'citevision-ai|run-ai-engine' 2>/dev/null || true
pkill -f 'rules-engine' 2>/dev/null || true
pkill -f 'citevision-api' 2>/dev/null || true
# free ports
for p in 5174 5175 8081 8001 8010; do
  fuser -k "${p}/tcp" 2>/dev/null || true
done
sleep 2
echo "[OK] app processes stopped"

# 3) Frigate / go2rtc / OCR d'abord (consommateurs média)
echo "=== [3/6] stop Frigate + go2rtc + OCR ==="
docker stop citevision-v2-frigate citevision-v2-go2rtc citevision-v2-ocr 2>/dev/null || true

# 4) Reste infra (garder volumes — pas de -v)
echo "=== [4/6] stop infra containers ==="
docker stop citevision-v2-mailhog citevision-v2-minio citevision-v2-mosquitto \
  citevision-v2-redis citevision-v2-postgres 2>/dev/null || true
(cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" stop 2>/dev/null) || true

# 5) Vérif ports libres
echo "=== [5/6] verify ports ==="
still=0
for p in 5174 8081 8001 8010 5000 1984; do
  if curl -sf --max-time 1 "http://127.0.0.1:${p}/" >/dev/null 2>&1 \
     || curl -sf --max-time 1 "http://127.0.0.1:${p}/health" >/dev/null 2>&1 \
     || curl -sf --max-time 1 "http://127.0.0.1:${p}/api/version" >/dev/null 2>&1; then
    echo "[WARN] port $p still answering"
    still=1
  fi
done
[[ "$still" = "0" ]] && echo "[OK] service ports quiet"

# 6) Résumé ressources (dockerd laissé vivant — redémarrage plus rapide)
echo "=== [6/6] summary ==="
docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | head -20 || echo "docker ps n/a"
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  STOP DONE — ressources libérées             ║"
echo "║  dockerd WSL laissé actif (volontaire)       ║"
echo "║  Relance: launcher\\Start-CiteVision.ps1      ║"
echo "╚══════════════════════════════════════════════╝"
exit 0
'@

$tmp = Join-Path $env:TEMP "citevision-stop-all.sh"
[System.IO.File]::WriteAllText($tmp, ($bash -replace "`r`n","`n" -replace "`r","`n"))
Get-Content -LiteralPath $tmp -Raw | wsl -d $Distro -- bash -c "cat > /tmp/citevision-stop-all.sh && sed -i 's/\r`$//' /tmp/citevision-stop-all.sh && CV_ROOT=$WslRoot bash /tmp/citevision-stop-all.sh"
exit $LASTEXITCODE
