# CitéVision v2 — Ensure AI stack (Windows → WSL required for AI)
param(
    [switch]$Fix,
    [switch]$VerifyOnly,
    [switch]$RestartAi,
    [int]$MaxAttempts = 5,
    [string]$HealthUrl = 'http://127.0.0.1:8001/health'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. (Join-Path $PSScriptRoot 'lib\resolve-wsl-path.ps1')

function Invoke-WslEnsure {
    param([string[]]$Args)
    $wslRoot = Get-WslProjectRoot -WindowsRoot $Root
    $argStr = ($Args | ForEach-Object { "'$_'" }) -join ' '
    wsl -- bash -lc "cd '$wslRoot' && bash scripts/ensure-ai-stack.sh $argStr"
    return $LASTEXITCODE
}

$ensureArgs = @()
if ($Fix) { $ensureArgs += '--fix' }
if ($VerifyOnly) { $ensureArgs += '--verify-only' }
if ($RestartAi) { $ensureArgs += '--restart-ai' }
$ensureArgs += "--max-attempts=$MaxAttempts"
$ensureArgs += "--health-url=$HealthUrl"

$wslOk = $false
try { $null = wsl --status 2>$null; $wslOk = ($LASTEXITCODE -eq 0) } catch { $wslOk = $false }

if (-not $wslOk) {
    if ($VerifyOnly -and -not $Fix) {
        Write-Host '[ERR] WSL2 requis pour vérifier la stack IA — installez WSL2 et relancez setup.bat' -ForegroundColor Red
        exit 1
    }
    Write-Host '[ERR] WSL2 requis pour la stack IA (InsightFace / PaddleOCR). Installez WSL2 et relancez setup.bat.' -ForegroundColor Red
    exit 1
}

$rc = Invoke-WslEnsure -Args $ensureArgs
exit $rc
