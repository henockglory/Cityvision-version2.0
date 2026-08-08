# Citevision v2 - stop via WSL runtime (ASCII-only for PS 5.1).
$ErrorActionPreference = 'Continue'

Write-Host "=== citevision Stop (Windows -> WSL) ==="
. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')
try {
    $WslRoot = Resolve-CiteVisionWslRoot
} catch {
    Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}

# Prefer stop-linux.sh when present; else no-op warn.
$bashCmd = ("cd '{0}'; if test -f scripts/stop-linux.sh; then bash scripts/stop-linux.sh; else echo '[WARN] stop-linux.sh missing'; exit 0; fi" -f $WslRoot)
& wsl.exe -- bash -lc $bashCmd
Write-Host "[OK] Stop requested via WSL"
exit $LASTEXITCODE
