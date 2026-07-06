# Citevision v2 — Windows: délègue tout à WSL (Docker Engine natif, pas Docker Desktop).
param(
    [switch]$SkipServices,
    [switch]$InfraOnly
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "=== Citevision v2 Start (Windows -> WSL) ==="
Write-Host "[INFO] Stack 100% WSL — Docker Engine natif, pas Docker Desktop."
Write-Host ""

$wslRoot = & wsl.exe wslpath -a $Root 2>$null
if (-not $wslRoot) { $wslRoot = '/mnt/c/Citevision' }

if ($InfraOnly -or $SkipServices) {
    Write-Host "[WARN] InfraOnly/SkipServices non implémentés — lancement stack complète via WSL"
}

& wsl.exe -- bash -lc "cd '$wslRoot' && bash scripts/start-linux.sh"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] start-linux.sh a échoué (code $LASTEXITCODE) — consultez logs/ dans WSL" -ForegroundColor Red
    exit $LASTEXITCODE
}
