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

Write-Host "[1/4] Runtime check" -ForegroundColor Cyan
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
Write-Host "[2/4] Refresh start scripts (max 25s)" -ForegroundColor Cyan
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
    cp -f "$s" "$d" 2>/dev/null || true
    echo "[OK] refreshed $rel"
  else
    echo "[INFO] skip missing $rel"
  fi
}
copy_one scripts/lib/start-full-stack.sh
copy_one scripts/lib/business-readiness.sh
copy_one scripts/lib/env-utils.sh
copy_one scripts/lib/service-heal.sh
copy_one scripts/lib/probe-gemini.sh
copy_one scripts/lib/set-gemini-key.sh
copy_one scripts/ensure-demo-pipeline.sh
copy_one scripts/ensure-ai-stack.sh
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
copy_one scripts/lib/compose-gpu.sh
copy_one infra/docker-compose.nvidia.yml
copy_one infra/frigate.base.yaml
copy_one scripts/apply-wsl-balanced-resources.ps1
echo "[OK] start scripts refresh done"
exit 0
'@

$syncTmp = Join-Path $env:TEMP "citevision-start-sync.sh"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($syncTmp, ($syncBash -replace "`r`n", "`n" -replace "`r", "`n"), $utf8NoBom)
$syncWsl = ConvertTo-WslPath $syncTmp
$syncCmd = ('sed "s/\r$//" "{0}" > /tmp/citevision-start-sync.sh; chmod +x /tmp/citevision-start-sync.sh; CV_SRC={1} CV_DST={2} timeout 25 bash /tmp/citevision-start-sync.sh || echo "[WARN] refresh timed out - continuing with runtime copy"' -f $syncWsl, $WslProductRoot, $WslRoot)
wsl -d $Distro -- bash -lc $syncCmd
Write-Host "[OK] Refresh step finished" -ForegroundColor Green
Write-Host ""

Write-Host "[3/4] Starting stack (live log below)" -ForegroundColor Cyan
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
Write-Host "[4/4] Start result" -ForegroundColor Cyan

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

Write-Host "[OK] CiteVision is ready" -ForegroundColor Green
Write-Host "     Open http://127.0.0.1:5174" -ForegroundColor Green
Write-Host ""
exit 0
