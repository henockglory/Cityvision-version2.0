# Citevision v2 - diagnostic Windows (sans WSL)
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. (Join-Path $PSScriptRoot 'lib\env-utils.ps1')

$Fail = 0
function Check($Name, $Ok, $Hint = '') {
    if ($Ok) { Write-Host "[PASS] $Name" }
    else { Write-Host "[FAIL] $Name"; if ($Hint) { Write-Host "       $Hint" }; $script:Fail++ }
}

Write-Host "=== Citevision v2 Doctor (Windows) ==="
Write-Host ""

$dockerOk = $false
try { docker info 2>$null | Out-Null; $dockerOk = $LASTEXITCODE -eq 0 } catch { }
if (-not $dockerOk) {
    $ddPaths = @(
        "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    )
    $ddFound = $ddPaths | Where-Object { Test-Path $_ }
    Check 'Docker daemon running' $false "Install/start Docker Desktop. Found: $($ddFound -join ', ')"
} else {
    Check 'Docker daemon running' $true
}

Check 'Go installed' (Get-Command go -ErrorAction SilentlyContinue) 'Install Go 1.22+'
Check 'Node installed' (Get-Command node -ErrorAction SilentlyContinue) 'Install Node 20+'
Check 'Python installed' (Get-Command python -ErrorAction SilentlyContinue) 'Install Python 3.12+'
Check 'FFmpeg installed' (Get-Command ffmpeg -ErrorAction SilentlyContinue) 'Optional for camera RTSP probe'

$ports = @{
    'PostgreSQL' = 5433
    'Redis'      = 6380
    'MQTT'       = 1884
    'MinIO API'  = 9003
    'go2rtc'     = 1984
    'Backend'    = 8081
    'AI Engine'  = 8001
    'Rules'      = 8010
    'Frontend'   = 5174
}
foreach ($p in $ports.GetEnumerator()) {
    $free = Test-PortFree $p.Value
    if ($free) { Write-Host "[PASS] Port $($p.Value) ($($p.Key)) free" }
    else { Write-Host "[WARN] Port $($p.Value) ($($p.Key)) in use" }
}

$envPath = Join-Path $Root '.env'
if (Test-Path $envPath) {
    Load-DotEnv $envPath
    Check 'JWT_SECRET set' ($env:JWT_SECRET -and $env:JWT_SECRET.Length -ge 16)
    Check 'AUDIT_SIGNING_KEY set' ($env:AUDIT_SIGNING_KEY -and $env:AUDIT_SIGNING_KEY.Length -ge 16)
    Check 'CAMERA_CREDENTIAL_KEY set' ($env:CAMERA_CREDENTIAL_KEY -and $env:CAMERA_CREDENTIAL_KEY.Length -ge 32)
    Check 'DATABASE_URL set' ($env:DATABASE_URL -or ($env:POSTGRES_USER -and $env:POSTGRES_DB))
} else {
    Check '.env exists' $false 'Run start-windows.ps1 to auto-generate from .env.example'
}

$camIp = $env:CAMERA_TEST_IP
if (-not $camIp) { $camIp = $env:TEST_CAMERA_IP }
if ($camIp) {
    $ping = Test-Connection -ComputerName $camIp -Count 1 -Quiet -ErrorAction SilentlyContinue
    Check "Camera ping $camIp" $ping "Verify network / VPN"
} else {
    Write-Host "[INFO] CAMERA_TEST_IP not set in .env - skip camera probe"
}

@(
    'backend/go.mod', 'frontend/package.json', 'rules-engine/go.mod',
    'ai-engine/pyproject.toml', 'infra/docker-compose.yml', 'docs/CLARIFICATIONS.md'
) | ForEach-Object {
    Check $_ (Test-Path (Join-Path $Root $_))
}

Write-Host ""
Write-Host "FAIL=$Fail"
if ($Fail -gt 0) { exit 1 }
