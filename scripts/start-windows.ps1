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

. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')
try {
    $WslRoot = Resolve-CiteVisionWslRoot
} catch {
    Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
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
