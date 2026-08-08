# Citevision v2 - Windows: delegate all to WSL (native dockerd, not Docker Desktop).
# ASCII-only for Windows PowerShell 5.1.
param(
    [switch]$SkipServices,
    [switch]$InfraOnly
)
$ErrorActionPreference = 'Stop'

Write-Host "=== Citevision v2 Start (Windows -> WSL) ==="
Write-Host "[INFO] Stack 100% WSL - native Docker Engine, not Docker Desktop."
Write-Host ""

# Prefer native runtime (R.1). Fall back only if missing.
$WslRoot = "/home/gheno/citevision-v2"
if ($WslRoot -match '^/mnt/[a-z]/') {
    Write-Host "[FAIL] Refuse WSL root under /mnt/* - use ~/citevision-v2" -ForegroundColor Red
    exit 1
}

$probe = ('test -f "{0}/scripts/start-linux.sh"' -f $WslRoot)
wsl -- bash -lc $probe
if ($LASTEXITCODE -ne 0) {
    Write-Host ("[FAIL] Missing {0}/scripts/start-linux.sh - run scripts/sync-to-wsl.sh" -f $WslRoot) -ForegroundColor Red
    exit 1
}

if ($InfraOnly -or $SkipServices) {
    Write-Host "[WARN] InfraOnly/SkipServices not implemented - launching full stack via WSL"
}

# PS 5.1-safe: use ';' not '&&'
$bashCmd = ("cd '{0}'; bash scripts/start-linux.sh" -f $WslRoot)
& wsl.exe -- bash -lc $bashCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host ("[FAIL] start-linux.sh failed (code {0}) - see logs/ in WSL" -f $LASTEXITCODE) -ForegroundColor Red
    exit $LASTEXITCODE
}
