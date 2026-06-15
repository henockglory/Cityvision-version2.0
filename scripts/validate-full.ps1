# Citevision v2 - validation complete (functional + build + perf)
param(
    [string]$BaseUrl = 'http://localhost:8081',
    [string]$FrontendUrl = 'http://localhost:5174',
    [switch]$SkipLiveStack
)
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. (Join-Path $PSScriptRoot 'lib\env-utils.ps1')

$Fail = 0
function Pass($n, $ok, $detail = '') {
    if ($ok) { Write-Host "[PASS] $n $detail" }
    else { Write-Host "[FAIL] $n $detail"; $script:Fail++ }
}

Write-Host "=== Citevision v2 Full Validation ==="
Write-Host ""

Push-Location backend; go test ./... -count=1; Pass 'F0 backend unit' ($LASTEXITCODE -eq 0); Pop-Location
Push-Location rules-engine; go test ./... -count=1; Pass 'F0 rules-engine unit' ($LASTEXITCODE -eq 0); Pop-Location
Push-Location ai-engine; python -m pytest tests/ -q --tb=no; Pass 'F0 ai-engine unit' ($LASTEXITCODE -eq 0); Pop-Location
Push-Location frontend; npm run build --silent; Pass 'F0 frontend build' ($LASTEXITCODE -eq 0); Pop-Location

if (Test-Path 'shared/rule-catalog') {
    $count = 0
    Get-ChildItem 'shared/rule-catalog/*.json' | ForEach-Object {
        $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
        $count += @($j).Count
    }
    Pass 'F6 rule catalog 20+' ($count -ge 20) "count=$count"
}

if (Test-Path 'frontend/src/data/mock.ts') { Pass 'no mock.ts' $false } else { Pass 'no mock.ts' $true }
$mockHits = Get-ChildItem -Path 'frontend/src' -Recurse -Include '*.ts','*.tsx' -File -ErrorAction SilentlyContinue |
    Select-String -Pattern 'demoLogin|withMockFallback' -SimpleMatch
if ($mockHits) { Pass 'zero mock patterns' $false } else { Pass 'zero mock patterns' $true }

if ($SkipLiveStack) {
    Write-Host "[INFO] SkipLiveStack - API/E2E tests skipped"
    Write-Host "FAIL=$Fail"
    if ($Fail -gt 0) { exit 1 }
    exit 0
}

try {
    $h = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 10
    Pass 'F1 API health' ($h.status -eq 'ok' -or $h.status -eq 'healthy')
} catch { Pass 'F1 API health' $false $_.Exception.Message }

try {
    $setup = Invoke-RestMethod -Uri "$BaseUrl/api/v1/setup/status" -TimeoutSec 10
    Pass 'F2 setup status endpoint' ($null -ne $setup.initialized)
} catch { Pass 'F2 setup status endpoint' $false }

try {
    $fe = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 10
    Pass 'F3 frontend HTTP' ($fe.StatusCode -eq 200)
} catch { Pass 'F3 frontend HTTP' $false }

$times = @()
1..10 | ForEach-Object {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 5 | Out-Null
        $sw.Stop()
        $times += $sw.ElapsedMilliseconds
    } catch { $sw.Stop(); $times += 9999 }
}
$p95 = ($times | Sort-Object)[9]
Pass 'perf API health p95 < 200ms' ($p95 -lt 200) "p95=${p95}ms"

Write-Host ""
Write-Host "FAIL=$Fail"
if ($Fail -gt 0) { exit 1 }
