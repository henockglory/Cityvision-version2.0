#Requires -Version 5.1
<#
.SYNOPSIS
  citevision - Uninstall (5 modes).

.PARAMETER Mode
  restart  : Restart services only (nothing removed)
  soft     : Stop + reset sentinels (keep volumes, venv, node_modules)
  standard : Stop + remove Docker volumes (keep venv, node_modules)
  full     : Remove venv + volumes (keep user data)
  nuclear  : Full removal including user data

.PARAMETER KeepData
  Keep Docker volumes (legacy compat).

.PARAMETER FromScratch
  Remove venv, node_modules, logs (legacy compat).

.PARAMETER KeepDeps
  Keep Python venv and node_modules.

.PARAMETER DeleteUserData
  Remove data/videos and data/evidence (nuclear mode).

.PARAMETER Yes
  Non-interactive mode.

.NOTES
  Requires Administrator rights.
#>
param(
    [ValidateSet('restart','soft','standard','full','nuclear','')]
    [string]$Mode = '',
    [switch]$KeepData,
    [switch]$FromScratch,
    [switch]$KeepDeps,
    [switch]$DeleteUserData,
    [switch]$Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

# Emit console output as UTF-8 so accented text is not garbled upstream.
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { $OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. (Join-Path $PSScriptRoot 'lib\resolve-wsl-path.ps1')

function Write-Log { param([string]$Msg, [string]$Level = 'INFO')
    Write-Host "[$Level] $Msg"
}

# -- Resolve flags from Mode --
if ($Mode -eq 'restart') {
    Write-Log 'Mode restart - restarting services only'
    Write-Log 'Stopping services...'
    wsl -- bash scripts/stop-linux.sh 2>$null
    Write-Log 'Starting services...'
    wsl -- bash scripts/start-linux.sh 2>$null
    Write-Log 'Services restarted'
    Write-Host ($(@{ ok = $true; mode = 'restart' }) | ConvertTo-Json -Compress)
    exit 0
} elseif ($Mode -eq 'soft') {
    $KeepData  = $true; $KeepDeps = $true
} elseif ($Mode -eq 'standard') {
    $KeepDeps  = $true
} elseif ($Mode -eq 'full') {
    $FromScratch = $true
} elseif ($Mode -eq 'nuclear') {
    $FromScratch = $true; $DeleteUserData = $true
}

# -- Check admin --
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]'Administrator')
if (-not $isAdmin) {
    Write-Log 'Administrator rights required for uninstall.' 'ERROR'
    exit 1
}

if (-not $Yes) {
    Write-Host ''
    Write-Host '=== citevision - Uninstall ==='
    if ($KeepData) {
        Write-Host 'Docker volumes will be KEPT.'
    } else {
        Write-Host 'WARNING: Docker volumes will be DELETED (data lost).'
    }
    $ans = Read-Host 'Continue? [y/N]'
    if ($ans -notmatch '^(o|oui|y|yes)$') {
        Write-Host 'Cancelled.'
        exit 0
    }
}

$summary = @{
    ok               = $true
    windows_svc      = 'skipped'
    wsl_stop         = 'skipped'
    wsl_svc          = 'skipped'
    docker           = 'skipped'
    keep_data        = [bool]$KeepData
    keep_deps        = [bool]$KeepDeps
    delete_user_data = [bool]$DeleteUserData
}

Write-Host ''
Write-Host '=== citevision - Uninstall ==='

# 1. Windows service
Write-Log 'Removing Windows service...'
$ps1 = Join-Path $Root 'installer\windows\uninstall-service.ps1'
if (Test-Path $ps1) {
    & $ps1
    if ($LASTEXITCODE -eq 0) { $summary.windows_svc = 'ok' } else { $summary.windows_svc = 'warn' }
} else {
    $summary.windows_svc = 'missing'
}

# 2. WSL stop + uninstall
$wslOk = $false
try {
    $null = wsl --status 2>$null
    $wslOk = $true
} catch { $wslOk = $false }

if ($wslOk) {
    Write-Log 'Stopping WSL services...'
    wsl -- bash scripts/stop-linux.sh 2>$null
    if ($LASTEXITCODE -eq 0) { $summary.wsl_stop = 'ok' } else { $summary.wsl_stop = 'warn' }

    Write-Log 'Removing WSL systemd service...'
    wsl -- sudo bash installer/linux/uninstall-service.sh 2>$null
    if ($LASTEXITCODE -eq 0) { $summary.wsl_svc = 'ok' } else { $summary.wsl_svc = 'warn' }

    if ($KeepData) {
        Write-Log 'Docker compose down (volumes kept)...'
        wsl -- bash -lc "cd '$($Root -replace '\\','/')' && docker compose -f infra/docker-compose.yml down" 2>$null
    } else {
        Write-Log 'Docker compose down -v (removing volumes)...'
        $wslRoot = Get-WslProjectRoot -WindowsRoot $Root
        wsl -- bash -lc "cd '$wslRoot' && docker compose -f infra/docker-compose.yml down -v" 2>$null
    }
    if ($LASTEXITCODE -eq 0) { $summary.docker = 'ok' } else { $summary.docker = 'warn' }

    Write-Log 'Removing sentinels...'
    $wslRoot = Get-WslProjectRoot -WindowsRoot $Root
    wsl -- bash -lc "cd '$wslRoot' && rm -f ai-engine/.venv/.installed_ok installer/.service_start_mode" 2>$null
    if ($FromScratch -and -not $KeepDeps) {
        Write-Log 'Full purge (venv, node_modules, logs)...'
        wsl -- bash -lc "cd '$wslRoot' && rm -rf ai-engine/.venv frontend/node_modules && rm -f generated.env && rm -f logs/*.log logs/*.pid && rm -rf ~/.citevision-v2 2>/dev/null || true" 2>$null
        $summary.from_scratch = 'ok'
    }
    if ($DeleteUserData) {
        Write-Log 'Removing user data (videos, evidence)...'
        wsl -- bash -lc "cd '$wslRoot' && rm -rf data/videos data/evidence 2>/dev/null || true" 2>$null
        $summary.delete_user_data = 'ok'
    }
} else {
    Write-Log 'WSL not available - skipping Linux steps' 'WARN'
    if (-not $KeepData) {
        Write-Log 'Docker compose down (local)...'
        docker compose -f infra/docker-compose.yml down -v 2>$null
        if ($LASTEXITCODE -eq 0) { $summary.docker = 'ok' }
    }
}

if ($FromScratch -and -not $KeepDeps -and -not $wslOk) {
    Write-Log 'Full purge (Windows local)...'
    Remove-Item -Recurse -Force (Join-Path $Root 'ai-engine\.venv') -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $Root 'frontend\node_modules') -ErrorAction SilentlyContinue
    Remove-Item -Force (Join-Path $Root 'generated.env') -ErrorAction SilentlyContinue
    Get-ChildItem (Join-Path $Root 'logs') -Filter '*.log' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem (Join-Path $Root 'logs') -Filter '*.pid' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}
if ($DeleteUserData -and -not $wslOk) {
    Write-Log 'Removing user data (Windows local)...'
    Remove-Item -Recurse -Force (Join-Path $Root 'data\videos') -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $Root 'data\evidence') -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Log 'Uninstall complete.'
Write-Log 'To reinstall: run setup.bat'
Write-Host ''
Write-Host ($summary | ConvertTo-Json -Compress)
exit 0
