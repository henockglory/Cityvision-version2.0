# Sync citevision Git repo to C:\Citevision runtime and restart WSL services.
# Usage: .\scripts\sync-demo-to-runtime.ps1

$ErrorActionPreference = "Stop"
$Source = Split-Path -Parent $PSScriptRoot
$Dest = "C:\Citevision"

function Sync-Dir($Relative) {
  $From = Join-Path $Source $Relative
  $To = Join-Path $Dest $Relative
  if (-not (Test-Path $From)) { return }
  Write-Host "  $Relative"
  robocopy $From $To /E /XD node_modules .git dist build target __pycache__ .venv /XF *.tsbuildinfo /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $Relative (exit $LASTEXITCODE)" }
}

Write-Host "==> Sync demo-related paths -> $Dest"
@("frontend", "backend", "scripts", "shared", "infra") | ForEach-Object { Sync-Dir $_ }

Write-Host "==> Restart API + frontend (WSL)"
wsl bash /mnt/c/Citevision/scripts/restart-api-frontend.sh

Write-Host "OK: synced and restarted. Open http://localhost:5174/demo (Ctrl+Shift+R)"
