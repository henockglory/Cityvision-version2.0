#Requires -Version 5.1
# Sync demo-related paths from Windows repo mirror to native WSL ~/citevision-v2.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\sync-demo-to-runtime.ps1
# ASCII-only. Never treats /mnt/* as runtime destination.

$ErrorActionPreference = "Stop"
$Source = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path

. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')
try {
    $WslRoot = Resolve-CiteVisionWslRoot
} catch {
    Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}

if ($WslRoot -match '^/mnt/') {
    Write-Host "[FAIL] Refuse runtime under /mnt/* - use native ~/citevision-v2" -ForegroundColor Red
    exit 1
}

function ConvertTo-WslMirrorPath {
    param([string]$winPath)
    $drive = $winPath[0].ToString().ToLower()
    $rest  = $winPath.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}

$SrcWsl = ConvertTo-WslMirrorPath $Source
$Dirs = @('frontend', 'backend', 'scripts', 'shared', 'infra')

Write-Host ("==> Sync demo paths -> native WSL {0}" -f $WslRoot)
foreach ($rel in $Dirs) {
    $from = "$SrcWsl/$rel/"
    $to = "$WslRoot/$rel/"
    $probe = ('test -d "{0}"' -f $from)
    & wsl.exe -- bash -lc $probe 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  skip missing {0}" -f $rel)
        continue
    }
    Write-Host ("  {0}" -f $rel)
    $rsync = @(
        "rsync -a --delete",
        "--exclude node_modules --exclude .git --exclude dist --exclude build",
        "--exclude target --exclude __pycache__ --exclude .venv",
        "--exclude '*.tsbuildinfo'",
        ("'{0}' '{1}'" -f $from, $to)
    ) -join ' '
    & wsl.exe -- bash -lc $rsync
    if ($LASTEXITCODE -ne 0) {
        throw ("rsync failed for {0} (exit {1})" -f $rel, $LASTEXITCODE)
    }
}

Write-Host "==> Restart API + frontend (WSL native runtime)"
$restartCmd = ("cd '{0}'; if test -f scripts/restart-api-frontend.sh; then bash scripts/restart-api-frontend.sh; else echo '[WARN] restart-api-frontend.sh missing'; fi" -f $WslRoot)
& wsl.exe -- bash -lc $restartCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host ("[WARN] restart exit={0}" -f $LASTEXITCODE)
}

Write-Host "OK: synced to native runtime. Open http://localhost:5174/demo (Ctrl+Shift+R)"
exit 0
