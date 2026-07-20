#Requires -Version 5.1
<#
.SYNOPSIS
  Start the full CiteVision stack via WSL orchestration.
.NOTES
  Runtime = WSL ~/citevision-v2 (scripts/lib/start-full-stack.sh).
  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1
  Exit 0 only when health_check_all is green (disk WARN allowed).
  ASCII-only strings for Windows PowerShell 5.1 encoding safety.
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
$WslRoot = "/home/gheno/citevision-v2"

Write-Host ""
Write-Host ("CiteVision START - WSL {0} (start-full-stack.sh)" -f $WslRoot) -ForegroundColor Cyan
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

# Use ';' not '&&' so Windows PowerShell 5.1 never mis-parses the command line.
$bashCmd = "cd '{0}'; bash scripts/lib/start-full-stack.sh" -f $WslRoot
wsl -d $Distro -- bash -lc $bashCmd
$rc = $LASTEXITCODE
if ($rc -ne 0) {
  Write-Host ""
  Write-Host ("[FAIL] start-full-stack exit={0} - see WSL logs {1}/logs" -f $rc, $WslRoot) -ForegroundColor Red
  exit $rc
}
Write-Host ""
Write-Host "[OK] Stack ready - UI http://127.0.0.1:5174" -ForegroundColor Green
exit 0
