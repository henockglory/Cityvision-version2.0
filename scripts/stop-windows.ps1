# Citevision v2 - stop via WSL runtime (ASCII-only for PS 5.1).
$ErrorActionPreference = 'Continue'
$WslRoot = "/home/gheno/citevision-v2"

Write-Host "=== citevision Stop (Windows -> WSL) ==="
if ($WslRoot -match '^/mnt/[a-z]/') {
    Write-Host "[FAIL] Refuse WSL root under /mnt/* - use ~/citevision-v2" -ForegroundColor Red
    exit 1
}

$probe = ('test -f "{0}/scripts/stop-linux.sh" -o -f "{0}/launcher/Stop-CiteVision.ps1"' -f $WslRoot)
wsl -- bash -lc $probe | Out-Null

# Prefer stop-linux.sh when present; else no-op warn.
$bashCmd = ("cd '{0}'; if test -f scripts/stop-linux.sh; then bash scripts/stop-linux.sh; else echo '[WARN] stop-linux.sh missing'; exit 0; fi" -f $WslRoot)
& wsl.exe -- bash -lc $bashCmd
Write-Host "[OK] Stop requested via WSL"
exit $LASTEXITCODE
