#Requires -Version 5.1
<#
.SYNOPSIS
  Démarre TOUTE la stack CitéVision via l'orchestration unique WSL.
.NOTES
  Runtime = WSL ~/citevision-v2 (même chemin que scripts/lib/start-full-stack.sh).
  Double-cliquer ou :
    powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1
  Quitte 0 seulement si health_check_all est vert (WARN disque toléré).
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
$WslRoot = "/home/gheno/citevision-v2"

Write-Host ""
Write-Host "CiteVision START — WSL $WslRoot (start-full-stack.sh)" -ForegroundColor Cyan
Write-Host ""

$prev = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
wsl -d $Distro -e true 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  $ErrorActionPreference = $prev
  Write-Host "[FAIL] Distro WSL '$Distro' inaccessible" -ForegroundColor Red
  exit 1
}
$ErrorActionPreference = $prev

wsl -d $Distro -e bash -lc "cd '$WslRoot' && bash scripts/lib/start-full-stack.sh"
$rc = $LASTEXITCODE
if ($rc -ne 0) {
  Write-Host ""
  Write-Host "[FAIL] start-full-stack exit=$rc — voir logs dans WSL $WslRoot/logs" -ForegroundColor Red
  exit $rc
}
Write-Host ""
Write-Host "[OK] Stack prête — UI http://127.0.0.1:5174" -ForegroundColor Green
exit 0
