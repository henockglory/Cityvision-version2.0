# Citevision v2 - full Windows start (Docker auto-start, no WSL)
param(
    [switch]$SkipServices,
    [switch]$InfraOnly
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. (Join-Path $PSScriptRoot 'lib\env-utils.ps1')

$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Write-Host "=== Citevision v2 Start (Windows) ==="
Write-Host ""

$envFile = Ensure-EnvFile $Root
Load-DotEnv $envFile

function Wait-Docker {
    param([int]$MaxSec = 90)
    $deadline = (Get-Date).AddSeconds($MaxSec)
    while ((Get-Date) -lt $deadline) {
        try {
            docker info 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch { }
        Start-Sleep -Seconds 3
    }
    return $false
}

$dockerReady = $false
try { docker info 2>$null | Out-Null; $dockerReady = ($LASTEXITCODE -eq 0) } catch { }

if (-not $dockerReady) {
    Write-Host "[INFO] Docker not running - starting Docker Desktop..."
    $dd = @(
        "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $dd) { throw 'Docker Desktop not found' }
    Start-Process $dd
    if (-not (Wait-Docker 90)) { throw 'Docker daemon not ready within 90s' }
    Write-Host "[OK] Docker daemon ready"
} else {
    Write-Host "[OK] Docker already running"
}

Write-Host "[INFO] Starting infrastructure..."
docker compose -f infra/docker-compose.yml --env-file $envFile up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
Write-Host "[OK] Infrastructure healthy"

if ($InfraOnly) {
    Write-Host "Infra only - PG:5433 Redis:6380 MQTT:1884 MinIO:9003 go2rtc:1984"
    exit 0
}

if ($SkipServices) {
    Write-Host "[INFO] SkipServices - infra only"
    exit 0
}

Write-Host "[INFO] Vérification / correction AI stack…"
& (Join-Path $PSScriptRoot 'ensure-ai-stack.ps1') -Fix -MaxAttempts 5
if ($LASTEXITCODE -ne 0) { throw 'AI stack incomplete after auto-fix' }
Write-Host "[OK] AI stack ready"

if (-not (Test-Path (Join-Path $Root 'frontend\node_modules'))) {
    Write-Host "[INFO] npm install frontend..."
    Push-Location (Join-Path $Root 'frontend')
    npm install --silent
    Pop-Location
}

$backendPort = if ($env:API_PORT) { $env:API_PORT } else { '8081' }
$aiPort = if ($env:AI_ENGINE_PORT) { $env:AI_ENGINE_PORT } else { '8001' }
$rulesPort = if ($env:RULES_ENGINE_PORT) { $env:RULES_ENGINE_PORT } else { '8010' }

Start-BackgroundProcess -Name 'backend' -WorkingDirectory (Join-Path $Root 'backend') `
    -Command 'go run ./cmd/api' -LogDir $LogDir

Start-Sleep -Seconds 3

Start-BackgroundProcess -Name 'rules-engine' -WorkingDirectory (Join-Path $Root 'rules-engine') `
    -Command 'go run ./cmd/rules-engine' -LogDir $LogDir

Start-BackgroundProcess -Name 'ai-engine' -WorkingDirectory (Join-Path $Root 'ai-engine') `
    -Command ".\.venv\Scripts\python.exe -m uvicorn citevision_ai.main:app --host 0.0.0.0 --port $aiPort" -LogDir $LogDir

Start-BackgroundProcess -Name 'frontend' -WorkingDirectory (Join-Path $Root 'frontend') `
    -Command 'npm run dev' -LogDir $LogDir

Write-Host ""
Write-Host "[INFO] Gate IA (YOLO + InsightFace + PaddleOCR)…"
& (Join-Path $PSScriptRoot 'ensure-ai-stack.ps1') -Fix -RestartAi -MaxAttempts 5 `
    -HealthUrl "http://127.0.0.1:$aiPort/health"
if ($LASTEXITCODE -ne 0) { throw 'AI gate not validated after auto-fix' }
Write-Host "[OK] AI gate validated"

Write-Host ""
Write-Host "[INFO] Waiting for backend health..."
if (Wait-HttpOk "http://localhost:$backendPort/health" 45) {
    Write-Host "[OK] Backend healthy"
} else {
    Write-Host "[WARN] Backend health timeout - check logs\backend.log"
}

Write-Host ""
Write-Host "=== Citevision v2 Running ==="
Write-Host "  Frontend:     http://localhost:5174"
Write-Host "  Setup:        http://localhost:5174/setup"
Write-Host "  Backend API:  http://localhost:$backendPort/health"
Write-Host "  AI Engine:    http://localhost:$aiPort/health"
Write-Host "  Rules Engine: http://localhost:$rulesPort/health"
Write-Host "  go2rtc:       http://localhost:1984"
Write-Host "  MinIO:        http://localhost:9004"
Write-Host ""
Write-Host "Stop: .\scripts\stop-windows.ps1"
