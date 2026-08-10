#Requires -Version 5.1
<#
.SYNOPSIS
  Start the full CiteVision stack via WSL orchestration.
.NOTES
  Runtime = WSL ~/citevision-v2 (scripts/lib/start-full-stack.sh).
  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1
  Exit 0 only when service gate + STRICT health + Gemini probe pass.
  ASCII-only strings for Windows PowerShell 5.1 encoding safety
  (except the user-facing API key placeholder which must match the plan literally).
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
Write-Host ("CiteVision START - WSL {0} (start-full-stack.sh STRICT)" -f $WslRoot) -ForegroundColor Cyan
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

# PS 5.1-safe probe: no && and no bash case *) inside the PowerShell source line.
$probe = ('test -f "{0}/scripts/lib/start-full-stack.sh"' -f $WslRoot)
wsl -d $Distro -- bash -lc $probe
if ($LASTEXITCODE -ne 0) {
  Write-Host ("[FAIL] Missing start-full-stack at {0} - sync to ~/citevision-v2" -f $WslRoot) -ForegroundColor Red
  exit 1
}

# Sync live-preview UI (go2rtc video-only; never embed Frigate SPA) into WSL runtime.
# Additive — does not weaken STRICT health / Gemini gate.
# Prefer Windows mirror script so first sync works even if WSL copy is stale.
$syncPreview = ('bash /mnt/c/Users/gheno/citevision/scripts/lib/sync-live-preview-ui.sh /mnt/c/Users/gheno/citevision "{0}"' -f $WslRoot)
Write-Host "[INFO] Sync live-preview UI -> WSL" -ForegroundColor DarkCyan
wsl -d $Distro -- bash -lc $syncPreview
if ($LASTEXITCODE -ne 0) {
  Write-Host "[WARN] live-preview sync failed — continuing with runtime copy" -ForegroundColor Yellow
}

# STRICT: face + Gemini configured/reachable are hard FAIL. Use ';' not '&&' for PS 5.1.
$bashCmd = ("cd '{0}'; export STRICT_INSTALL_HEALTH=1; bash scripts/lib/start-full-stack.sh" -f $WslRoot)
$startOut = wsl -d $Distro -- bash -lc $bashCmd 2>&1
$rc = $LASTEXITCODE
Write-Host ($startOut | Out-String)

if ($rc -ne 0) {
  Write-Host ""
  Write-Host ("[FAIL] start-full-stack exit={0} - see WSL logs {1}/logs" -f $rc, $WslRoot) -ForegroundColor Red
  $joined = ($startOut | Out-String)
  if ($joined -match 'GEMINI_PROBE_FAILED|gemini_probe FAILED|gemini_configured missing|GEMINI_PROBE') {
    Write-Host ""
    Write-Host "[FAIL] Gemini indisponible (cle absente/invalide ou API injoignable)." -ForegroundColor Red
    Write-Host "Remplacez le placeholder puis executez:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Set-CiteVisionGeminiKey.ps1 -ApiKey 'saisissez votre nouvelle clé API'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Puis relancez:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1" -ForegroundColor Cyan
    Write-Host ""
  }
  exit $rc
}
Write-Host ""
Write-Host "[OK] Stack ready - UI http://127.0.0.1:5174" -ForegroundColor Green
exit 0
