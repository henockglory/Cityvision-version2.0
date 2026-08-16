#Requires -Version 5.1
<#
.SYNOPSIS
  Start the CiteVision product stack.
.NOTES
  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1
  Exit 0 when services, health gate, and Gemini probe pass.
  ASCII-only body for Windows PowerShell 5.1 encoding safety (like Stop-CiteVision.ps1).
  Streams WSL stdout live (no PowerShell line filter pipeline).
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')

function ConvertTo-WslPath {
  param([Parameter(Mandatory = $true)][string]$WinPath)
  $full = [System.IO.Path]::GetFullPath($WinPath)
  if ($full -match '^([A-Za-z]):\\?(.*)$') {
    $drive = $Matches[1].ToLowerInvariant()
    $rest = ($Matches[2] -replace '\\', '/')
    return ("/mnt/{0}/{1}" -f $drive, $rest).TrimEnd('/')
  }
  return ($full -replace '\\', '/')
}

function Resolve-CiteVisionProductRoot {
  # Installer tree (C:\Citevision) is often a stale copy of the git workspace.
  # Prefer %USERPROFILE%\citevision-v2 when present so Start never downgrades WSL scripts.
  if (-not [string]::IsNullOrWhiteSpace($env:CITEVISION_PRODUCT_ROOT) -and
      (Test-Path -LiteralPath (Join-Path $env:CITEVISION_PRODUCT_ROOT 'scripts\lib\start-full-stack.sh'))) {
    return [System.IO.Path]::GetFullPath($env:CITEVISION_PRODUCT_ROOT)
  }
  $installerRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
  $devRoot = Join-Path $env:USERPROFILE 'citevision-v2'
  $marker = 'scripts\lib\start-full-stack.sh'
  if (Test-Path -LiteralPath (Join-Path $devRoot $marker)) {
    return [System.IO.Path]::GetFullPath($devRoot)
  }
  return $installerRoot
}

try {
  $WslRoot = Resolve-CiteVisionWslRoot
} catch {
  Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
  exit 1
}

$ProductRoot = Resolve-CiteVisionProductRoot
$WslProductRoot = ConvertTo-WslPath $ProductRoot

Write-Host ""
Write-Host ("CiteVision START - WSL {0}" -f $WslRoot) -ForegroundColor Cyan
Write-Host ("Product mirror (refresh SRC): {0}" -f $ProductRoot) -ForegroundColor DarkGray
Write-Host ""

Write-Host "[1/5] Runtime check" -ForegroundColor Cyan
$prev = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
wsl -d $Distro -e true 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  $ErrorActionPreference = $prev
  Write-Host "[FAIL] Runtime environment is not available." -ForegroundColor Red
  exit 1
}
$ErrorActionPreference = $prev

$probe = ('test -f "{0}/scripts/lib/start-full-stack.sh"' -f $WslRoot)
wsl -d $Distro -- bash -lc $probe
if ($LASTEXITCODE -ne 0) {
  Write-Host "[FAIL] CiteVision runtime is incomplete. Reinstall or repair the product." -ForegroundColor Red
  exit 1
}
Write-Host "[OK] Runtime ready" -ForegroundColor Green

# Bounded refresh only (never hang Start on /mnt rsync of whole trees).
Write-Host "[2/5] Refresh start scripts (max 45s)" -ForegroundColor Cyan
$syncBash = @'
#!/usr/bin/env bash
set -uo pipefail
SRC="${CV_SRC:-}"
DST="${CV_DST:-$HOME/citevision-v2}"
if [[ -z "$SRC" || ! -d "$SRC" ]]; then
  echo "[WARN] product mirror unavailable - using runtime as-is"
  exit 0
fi
# Fast cp of start-critical scripts only; timeout wrapper kills hung /mnt IO.
copy_one() {
  local rel="$1"
  local s="$SRC/$rel"
  local d="$DST/$rel"
  if [[ -f "$s" ]]; then
    mkdir -p "$(dirname "$d")"
    # Always strip CR: Windows /mnt/c copies often inject CRLF and break bash watchdogs.
    if [[ "$rel" == *.sh || "$rel" == *.py || "$rel" == *.mjs ]]; then
      sed 's/\r$//' "$s" >"$d" 2>/dev/null || cp -f "$s" "$d" 2>/dev/null || true
    else
      cp -f "$s" "$d" 2>/dev/null || true
    fi
    echo "[OK] refreshed $rel"
  else
    echo "[INFO] skip missing $rel"
  fi
}
copy_one scripts/lib/start-full-stack.sh
copy_one scripts/lib/business-readiness.sh
copy_one scripts/lib/env-utils.sh
copy_one scripts/lib/service-heal.sh
copy_one scripts/lib/ensure-backend-bin.sh
copy_one scripts/lib/frontend-dist-stamp.sh
copy_one scripts/lib/heal-frigate-record.sh
copy_one scripts/lib/ensure-ai-src-fresh.sh
copy_one scripts/lib/frigate_detect_gate.py
copy_one scripts/lib/probe-gemini.sh
copy_one scripts/lib/set-gemini-key.sh
copy_one scripts/ensure-demo-pipeline.sh
copy_one scripts/ensure-ai-stack.sh
copy_one scripts/ensure-frontend.sh
copy_one scripts/serve-frontend-static.mjs
copy_one frontend/src/hooks/useAlertWebSocket.ts
copy_one frontend/src/hooks/api/queries.ts
copy_one frontend/src/pages/Alerts.tsx
copy_one scripts/watch-frontend.sh
copy_one scripts/watch-backend.sh
copy_one scripts/lib/platform-models-ok.py
copy_one frontend/vite.config.ts
copy_one scripts/health_check_all.sh
copy_one scripts/frigate_watchdog.sh
copy_one scripts/watch-infra-ports.sh
copy_one scripts/watch-ai-ingest.sh
copy_one scripts/watch-business-readiness.sh
copy_one scripts/watch-rules-engine.sh
copy_one scripts/_start-rules-engine.sh
copy_one scripts/watch-api.sh
copy_one scripts/watch-ai.sh
copy_one scripts/watch-rules.sh
copy_one scripts/validate_demo_1hit_seven_reactive.py
copy_one scripts/validate_demo_five_rules.py
copy_one scripts/_p7_reactive.sh
# Hyper-reactive demo pipeline (Frigate focus + fast evidence + lf_or_g feu)
copy_one ai-engine/src/citevision_ai/frigate_bridge/bridge.py
copy_one ai-engine/src/citevision_ai/frigate_bridge/snapshot.py
copy_one ai-engine/src/citevision_ai/bridge.py
copy_one ai-engine/src/citevision_ai/pipeline.py
copy_one ai-engine/src/citevision_ai/identity/plate_fusion.py
copy_one ai-engine/src/citevision_ai/identity/plate.py
copy_one ai-engine/src/citevision_ai/utils/paddle_ocr_compat.py
copy_one ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py
copy_one ai-engine/src/citevision_ai/evidence/capture.py
copy_one ai-engine/src/citevision_ai/evidence/gate.py
copy_one ai-engine/src/citevision_ai/analytics/zone_geometry.py
copy_one ai-engine/src/citevision_ai/vlm/gemini_client.py
copy_one ai-engine/src/citevision_ai/vlm/queue.py
copy_one ai-engine/src/citevision_ai/road_enforcement/red_light_vote.py
copy_one backend/internal/frigate/detect_gate.go
copy_one backend/internal/frigate/sync.go
copy_one backend/internal/frigate/compiler.go
copy_one scripts/lib/compose-gpu.sh
copy_one infra/docker-compose.nvidia.yml
copy_one infra/frigate.base.yaml
copy_one scripts/apply-wsl-balanced-resources.ps1
copy_one frontend/src/components/StackHealthGate.tsx
copy_one frontend/src/i18n/locales/fr.json
copy_one frontend/src/i18n/locales/en.json
echo "[OK] start scripts refresh done"
exit 0
'@

$syncTmp = Join-Path $env:TEMP "citevision-start-sync.sh"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($syncTmp, ($syncBash -replace "`r`n", "`n" -replace "`r", "`n"), $utf8NoBom)
$syncWsl = ConvertTo-WslPath $syncTmp
$syncCmd = ('sed "s/\r$//" "{0}" > /tmp/citevision-start-sync.sh; chmod +x /tmp/citevision-start-sync.sh; CV_SRC={1} CV_DST={2} timeout 45 bash /tmp/citevision-start-sync.sh || echo "[WARN] refresh timed out - continuing with runtime copy"' -f $syncWsl, $WslProductRoot, $WslRoot)
wsl -d $Distro -- bash -lc $syncCmd
Write-Host "[OK] Refresh step finished" -ForegroundColor Green
Write-Host ""

# Force WSL RAM profile when still below 20GB (OOM killed Vite under 12GB). Needs wsl --shutdown once.
$wslCfgPath = Join-Path $env:USERPROFILE '.wslconfig'
$wslCfgText = ''
if (Test-Path -LiteralPath $wslCfgPath) {
  $wslCfgText = Get-Content -LiteralPath $wslCfgPath -Raw -ErrorAction SilentlyContinue
}
if ($wslCfgText -notmatch '(?im)^\s*memory\s*=\s*20GB\s*$') {
  Write-Host "[INFO] Updating .wslconfig to memory=20GB (apply with: wsl --shutdown)" -ForegroundColor Yellow
  $applyPs1 = Join-Path $ProductRoot 'scripts\apply-wsl-balanced-resources.ps1'
  if (Test-Path -LiteralPath $applyPs1) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $applyPs1
  }
}

Write-Host "[3/5] Starting stack (live log below)" -ForegroundColor Cyan
Write-Host ""

# Stop-like: script on disk, stdout streams live to this console (no ForEach filter).
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
cd "$ROOT" || { echo "[FAIL] cannot cd ROOT"; exit 1; }
export STRICT_INSTALL_HEALTH=1
export PYTHONUNBUFFERED=1
export CITEVISION_ASCII_LOG=1
if command -v stdbuf >/dev/null 2>&1; then
  stdbuf -oL -eL bash scripts/lib/start-full-stack.sh
  ec=$?
else
  bash scripts/lib/start-full-stack.sh
  ec=$?
fi
echo "__CV_START_EXIT__=${ec}"
exit "$ec"
'@

$tmp = Join-Path $env:TEMP "citevision-start-all.sh"
[System.IO.File]::WriteAllText($tmp, ($bash -replace "`r`n", "`n" -replace "`r", "`n"), $utf8NoBom)
$startWsl = ConvertTo-WslPath $tmp

# Direct wsl invoke (stdin free) so logs scroll like Stop-CiteVision.ps1
$remoteCmd = ('sed "s/\r$//" "{0}" > /tmp/citevision-start-all.sh; chmod +x /tmp/citevision-start-all.sh; CV_ROOT={1} bash /tmp/citevision-start-all.sh' -f $startWsl, $WslRoot)
& wsl.exe -d $Distro -- bash -lc $remoteCmd
$rc = $LASTEXITCODE

Write-Host ""
Write-Host "[4/5] Start result" -ForegroundColor Cyan

if ($rc -ne 0) {
  Write-Host "[FAIL] CiteVision could not start completely." -ForegroundColor Red
  if ($rc -eq 42) {
    Write-Host ""
    Write-Host "[FAIL] Vision AI key missing or unreachable." -ForegroundColor Red
    Write-Host "Set your API key, then start again:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Set-CiteVisionGeminiKey.ps1 -ApiKey 'YOUR_API_KEY'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1" -ForegroundColor Cyan
    Write-Host ""
  }
  exit $rc
}

# Definitive Windows gate: browser uses localhost from Windows, not only WSL curl.
Write-Host "[5/5] Windows UI + /health/platform" -ForegroundColor Cyan
$uiOk = $false
$platformUrl = 'http://127.0.0.1:5174/health/platform'
function Test-WslPlatformOk {
  $cmd = @'
curl -sf --max-time 5 http://127.0.0.1:5174/health/platform 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); detail=((d.get("components") or {}).get("ai_engine") or {}).get("detail") or {}; raise SystemExit(0 if str(detail.get("models_all_ok","")).lower()=="true" else 1)'
'@
  wsl -d $Distro -- bash -lc $cmd 2>$null | Out-Null
  return ($LASTEXITCODE -eq 0)
}

for ($i = 1; $i -le 45; $i++) {
  try {
    $resp = Invoke-WebRequest -Uri $platformUrl -UseBasicParsing -TimeoutSec 5
    # API returns models_all_ok as string "true" under components.ai_engine.detail
    if ($resp.StatusCode -eq 200 -and $resp.Content -match '"models_all_ok"\s*:\s*"?true"?') {
      $uiOk = $true
      break
    }
  } catch {}
  if (($i % 5) -eq 0) {
    Write-Host ("  retry {0}/45 - waking UI in WSL..." -f $i) -ForegroundColor DarkGray
    $healCmd = ('bash "{0}/scripts/ensure-frontend.sh"' -f $WslRoot)
    wsl -d $Distro -- bash -lc $healCmd 2>$null | Out-Null
    # Touch from WSL then Windows to re-bind localhostForwarding after UI restart.
    wsl -d $Distro -- bash -lc 'curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null' 2>$null | Out-Null

    # After Heal-DiskC / stuck wslrelay: WSL UI can be healthy while Windows localhostForwarding is dead.
    # Detect early (attempt 10+) and recycle WSL once so a fresh relay is created.
    if ($i -ge 10 -and $env:CV_LOCALHOST_HEAL_DONE -ne '1') {
      $wslOk = Test-WslPlatformOk
      if ($wslOk) {
        Write-Host "[WARN] WSL UI is healthy but Windows localhost:5174 is broken (stale wslrelay)." -ForegroundColor Yellow
        Write-Host "       Resetting WSL localhostForwarding once, then restarting the stack..." -ForegroundColor Yellow
        $env:CV_LOCALHOST_HEAL_DONE = '1'
        wsl --shutdown
        Start-Sleep -Seconds 5
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
        exit $LASTEXITCODE
      }
    }
  }
  Start-Sleep -Seconds 2
}

if (-not $uiOk) {
  Write-Host "[FAIL] Windows cannot reach http://127.0.0.1:5174/health/platform with models_all_ok." -ForegroundColor Red
  Write-Host "       Stack may be up in WSL but the Windows browser path is broken." -ForegroundColor Yellow
  Write-Host "       Check: wsl --shutdown then Start again; ensure .wslconfig has localhostForwarding=true and memory=20GB." -ForegroundColor Yellow
  exit 1
}

Write-Host "[OK] CiteVision is ready (Windows UI + platform models OK)" -ForegroundColor Green
Write-Host "     Open http://127.0.0.1:5174" -ForegroundColor Green
Write-Host ""
exit 0
