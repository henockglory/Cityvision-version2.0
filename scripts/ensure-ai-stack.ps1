# CitéVision v2 — Ensure AI stack (Windows native + WSL fallback)
param(
    [switch]$Fix,
    [switch]$VerifyOnly,
    [switch]$RestartAi,
    [int]$MaxAttempts = 5,
    [string]$HealthUrl = 'http://127.0.0.1:8001/health'
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-WslEnsure {
    param([string[]]$Args)
    $wslRoot = (wsl -- wslpath -a $Root 2>$null)
    if (-not $wslRoot) { $wslRoot = '/mnt/c/Users/gheno/citevision-v2' }
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

# Prefer WSL (same path as installateur 7315)
$wslOk = $false
try { $null = wsl --status 2>$null; $wslOk = $true } catch { $wslOk = $false }

if ($wslOk) {
    $rc = Invoke-WslEnsure -Args $ensureArgs
    exit $rc
}

# Native Windows fallback
$venvPy = Join-Path $Root 'ai-engine\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host '[FIX] Creating AI venv…'
    Push-Location (Join-Path $Root 'ai-engine')
    python -m venv .venv
    Pop-Location
}

if ($Fix) {
    Write-Host '[FIX] pip install extras (identity + anpr)…'
    & (Join-Path $Root 'ai-engine\.venv\Scripts\pip.exe') install -e "$Root\ai-engine\.[identity,anpr,dev]"
    if (Test-Path (Join-Path $Root 'scripts\download-models.sh')) {
        bash (Join-Path $Root 'scripts\download-models.sh') --skip-yolo
    }
}

if ($VerifyOnly -and -not $Fix) {
    & $venvPy -c "import citevision_ai, insightface, paddleocr" 2>$null
    exit $LASTEXITCODE
}

Write-Host '[OK] ensure-ai-stack.ps1 complete'
exit 0
