#Requires -Version 5.1
<#
.SYNOPSIS
  CitéVision v2 — Désinstallation complète (Windows + WSL).

.PARAMETER KeepData
  Conserve les volumes Docker.

.PARAMETER Yes
  Mode non interactif.

.NOTES
  Requiert des droits Administrateur.
#>
param(
    [switch]$KeepData,
    [switch]$Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Log { param([string]$Msg, [string]$Level = 'INFO')
    Write-Host "[$Level] $Msg"
}

# ── Vérifier admin ────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]'Administrator')
if (-not $isAdmin) {
    Write-Log 'Droits administrateur requis pour la désinstallation.' 'ERROR'
    exit 1
}

if (-not $Yes) {
    Write-Host ''
    Write-Host '=== CitéVision v2 — Désinstallation ==='
    if ($KeepData) {
        Write-Host 'Les volumes Docker seront CONSERVÉS.'
    } else {
        Write-Host 'ATTENTION : les volumes Docker seront SUPPRIMÉS (données perdues).'
    }
    $ans = Read-Host 'Continuer ? [o/N]'
    if ($ans -notmatch '^(o|oui|y|yes)$') {
        Write-Host 'Annulé.'
        exit 0
    }
}

$summary = @{
    ok           = $true
    windows_svc  = 'skipped'
    wsl_stop     = 'skipped'
    wsl_svc      = 'skipped'
    docker       = 'skipped'
    keep_data    = [bool]$KeepData
}

Write-Host ''
Write-Host '=== CitéVision v2 — Désinstallation ==='

# 1. Service Windows
Write-Log 'Suppression service Windows…'
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
    Write-Log 'Arrêt services WSL…'
    wsl -- bash scripts/stop-linux.sh 2>$null
    if ($LASTEXITCODE -eq 0) { $summary.wsl_stop = 'ok' } else { $summary.wsl_stop = 'warn' }

    Write-Log 'Suppression service systemd WSL…'
    wsl -- sudo bash installer/linux/uninstall-service.sh 2>$null
    if ($LASTEXITCODE -eq 0) { $summary.wsl_svc = 'ok' } else { $summary.wsl_svc = 'warn' }

    if ($KeepData) {
        Write-Log 'Docker compose down (volumes conservés)…'
        wsl -- bash -lc "cd '$($Root -replace '\\','/')' && docker compose -f infra/docker-compose.yml down" 2>$null
    } else {
        Write-Log 'Docker compose down -v…'
        $wslRoot = (wsl -- wslpath -a $Root 2>$null)
        if (-not $wslRoot) { $wslRoot = "/mnt/c/Users/gheno/citevision-v2" }
        wsl -- bash -lc "cd '$wslRoot' && docker compose -f infra/docker-compose.yml down -v" 2>$null
    }
    if ($LASTEXITCODE -eq 0) { $summary.docker = 'ok' } else { $summary.docker = 'warn' }

    Write-Log 'Suppression sentinelles…'
    wsl -- bash -lc "rm -f ai-engine/.venv/.installed_ok installer/.service_start_mode" 2>$null
} else {
    Write-Log 'WSL non disponible — étapes Linux ignorées' 'WARN'
    if (-not $KeepData) {
        Write-Log 'Docker compose down (local)…'
        docker compose -f infra/docker-compose.yml down -v 2>$null
        if ($LASTEXITCODE -eq 0) { $summary.docker = 'ok' }
    }
}

Write-Host ''
Write-Log 'Désinstallation terminée.'
Write-Log 'Pour réinstaller : lancez setup.bat'
Write-Host ''
Write-Host ($summary | ConvertTo-Json -Compress)
exit 0
