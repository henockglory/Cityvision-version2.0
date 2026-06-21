# Citévision v2 — arrêt services Windows
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. (Join-Path $PSScriptRoot 'lib\env-utils.ps1')

Write-Host "=== citevision Stop ==="

$LogDir = Join-Path $Root 'logs'
@('frontend', 'ai-engine', 'rules-engine', 'backend') | ForEach-Object {
    Stop-ProcessFromPidFile (Join-Path $LogDir "$_.pid")
}

Write-Host "[INFO] Stopping Docker infrastructure..."
docker compose -f infra/docker-compose.yml down 2>$null
Write-Host "[OK] Stopped"
