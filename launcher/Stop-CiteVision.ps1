#Requires -Version 5.1
<#
.SYNOPSIS
  Stop the full CiteVision stack safely (free CPU/GPU/RAM/disk).
.NOTES
  Runtime = WSL ~/citevision-v2.
  powershell -ExecutionPolicy Bypass -File launcher\Stop-CiteVision.ps1
  ASCII-only strings for Windows PowerShell 5.1 encoding safety.
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')
try {
  $WslRoot = Resolve-CiteVisionWslRoot
} catch {
  Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host ("CiteVision STOP - WSL {0}" -f $WslRoot) -ForegroundColor Cyan
Write-Host ""

$prev = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
wsl -d $Distro -e true 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  $ErrorActionPreference = $prev
  Write-Host ("[FAIL] WSL distro '{0}' not available" -f $Distro) -ForegroundColor Red
  exit 1
}
$ErrorActionPreference = $prev

# PS 5.1-safe probe: no && / case *) in the PowerShell source line.
$probe = ('test -d "{0}" -a -f "{0}/scripts/lib/start-full-stack.sh"' -f $WslRoot)
wsl -d $Distro -- bash -lc $probe
if ($LASTEXITCODE -ne 0) {
  Write-Host ("[FAIL] Missing runtime at {0} - sync to ~/citevision-v2" -f $WslRoot) -ForegroundColor Red
  exit 1
}

# Bash body as single-quoted here-string (PS does not expand). ASCII only.
$bash = @'
#!/usr/bin/env bash
set -uo pipefail
ROOT="${CV_ROOT:-$HOME/citevision-v2}"
case "$ROOT" in
  /mnt/*)
    echo "[FAIL] Refuse ROOT under /mnt/* (got $ROOT)"
    exit 1
    ;;
esac
cd "$ROOT" || { echo "[FAIL] ROOT=$ROOT"; exit 1; }
# shellcheck source=/dev/null
source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true
ENV_FILE="${ROOT}/.env"
KEY="changeme_internal_service_key"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | sed 's/\r$//')
  set +a
  KEY="${INTERNAL_API_KEY:-$KEY}"
fi
LOGDIR="$ROOT/logs"

echo "=== CiteVision STOP ALL $(date -Is) ==="
echo "ROOT=$ROOT"
# Never touch .env / Gemini keyfiles — Stop must not erase GEMINI_API_KEY.
rm -f "$LOGDIR/rules-engine.restart-request" 2>/dev/null || true

echo "=== [1/6] disable demo rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Demo%';" 2>/dev/null \
  || echo "[WARN] postgres unavailable for disable rules"

echo "=== [2/6] stop watchdogs / frontend / AI / rules / backend ==="
for svc in watch-demo-stack watch-backend watch-ai-ingest watch-rules-engine watch-infra-ports watch-business-readiness frigate-watchdog frontend ai-engine rules-engine backend; do
  if [[ -f "$LOGDIR/${svc}.pid" ]]; then
    pid=$(cat "$LOGDIR/${svc}.pid" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]]; then kill "$pid" 2>/dev/null || true; fi
    rm -f "$LOGDIR/${svc}.pid"
  fi
done
pkill -f 'watch-backend|watch-ai-ingest|watch-demo-stack|watch-rules-engine|watch-infra-ports|watch-business-readiness|frigate_watchdog|frigate-watchdog' 2>/dev/null || true
pkill -f 'vite|ensure-frontend' 2>/dev/null || true
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
pkill -f 'citevision-ai|run-ai-engine' 2>/dev/null || true
pkill -f 'rules-engine' 2>/dev/null || true
pkill -f 'citevision-api' 2>/dev/null || true
for p in 5174 5175 8081 8001 8010; do
  fuser -k "${p}/tcp" 2>/dev/null || true
done
sleep 2
echo "[OK] app processes stopped"

echo "=== [3/6] stop Frigate + go2rtc + OCR ==="
docker stop citevision-v2-frigate citevision-v2-go2rtc citevision-v2-ocr 2>/dev/null || true
# rm go2rtc so orphan docker-proxy cannot hold 1984/8554/8555 for next Start
docker rm -f citevision-v2-go2rtc 2>/dev/null || true
if declare -F free_port >/dev/null 2>&1; then
  free_port 1984 8554 8555 2>/dev/null || true
fi
if command -v fuser >/dev/null 2>&1; then
  fuser -k 1984/tcp 8554/tcp 8555/tcp 8555/udp 2>/dev/null || true
fi

echo "=== [4/6] stop infra containers ==="
docker stop citevision-v2-mailhog citevision-v2-minio citevision-v2-mosquitto \
  citevision-v2-redis citevision-v2-postgres 2>/dev/null || true
(cd "$ROOT/infra" ; docker compose --env-file "$ENV_FILE" stop 2>/dev/null) || true

echo "=== [5/6] verify ports ==="
still=0
for p in 5174 8081 8001 8010 5000 1984 8554 8555; do
  if curl -sf --max-time 1 "http://127.0.0.1:${p}/" >/dev/null 2>&1 \
     || curl -sf --max-time 1 "http://127.0.0.1:${p}/health" >/dev/null 2>&1 \
     || curl -sf --max-time 1 "http://127.0.0.1:${p}/api/version" >/dev/null 2>&1 \
     || curl -sf --max-time 1 "http://127.0.0.1:${p}/api" >/dev/null 2>&1; then
    echo "[WARN] port $p still answering"
    still=1
  fi
done
if [[ "$still" = "0" ]]; then
  echo "[OK] service ports quiet"
fi

echo "=== [6/6] summary ==="
docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | head -20 || echo "docker ps n/a"
echo ""
echo "=== STOP DONE - dockerd WSL left running ==="
echo "Restart: launcher\\Start-CiteVision.ps1"
echo "[OK] .env / Gemini keyfiles preserved"
exit 0
'@

$tmp = Join-Path $env:TEMP "citevision-stop-all.sh"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($tmp, ($bash -replace "`r`n", "`n" -replace "`r", "`n"), $utf8NoBom)

function ConvertTo-WslPathLocal {
  param([Parameter(Mandatory = $true)][string]$WinPath)
  $full = [System.IO.Path]::GetFullPath($WinPath)
  if ($full -match '^([A-Za-z]):\\?(.*)$') {
    $drive = $Matches[1].ToLowerInvariant()
    $rest = ($Matches[2] -replace '\\', '/')
    return ("/mnt/{0}/{1}" -f $drive, $rest).TrimEnd('/')
  }
  return ($full -replace '\\', '/')
}

# Direct path (no stdin pipe) so LASTEXITCODE is reliable and logs scroll live.
$stopWsl = ConvertTo-WslPathLocal $tmp
$remoteCmd = ('sed "s/\r$//" "{0}" > /tmp/citevision-stop-all.sh; chmod +x /tmp/citevision-stop-all.sh; CV_ROOT={1} bash /tmp/citevision-stop-all.sh; ec=$?; echo __CV_STOP_EXIT__=$ec; exit $ec' -f $stopWsl, $WslRoot)
& wsl.exe -d $Distro -- bash -lc $remoteCmd
$rc = $LASTEXITCODE
if ($null -eq $rc) { $rc = 1 }
if ($rc -ne 0) {
  Write-Host ("[FAIL] stop exit={0}" -f $rc) -ForegroundColor Red
  exit $rc
}
Write-Host "[OK] Stack stopped" -ForegroundColor Green
exit 0
