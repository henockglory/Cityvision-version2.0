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
# Native WSL tree only (R.1). Never start from /mnt/c Windows mirrors.
$WslRoot = "/home/gheno/citevision-v2"
if ($WslRoot -match '^/mnt/[a-z]/') {
  Write-Host "[FAIL] Refuse WSL root under /mnt/* — use ~/citevision-v2" -ForegroundColor Red
  exit 1
}

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

# Refuse accidental /mnt/c runtime; require native ~/citevision-v2 tree.
$probe = "test -f '{0}/scripts/lib/start-full-stack.sh' && case '{0}' in /mnt/*) exit 2;; *) exit 0;; esac" -f $WslRoot
wsl -d $Distro -- bash -lc $probe
if ($LASTEXITCODE -eq 2) {
  Write-Host "[FAIL] Runtime under /mnt/* forbidden — sync to ~/citevision-v2" -ForegroundColor Red
  exit 1
}
if ($LASTEXITCODE -ne 0) {
  Write-Host ("[FAIL] Missing start-full-stack at {0}" -f $WslRoot) -ForegroundColor Red
  exit 1
}

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
