#Requires -Version 5.1
<#
.SYNOPSIS
  CitéVision v2 — Désinstallation (5 modes).

.PARAMETER Mode
  restart  : Redémarre les services uniquement (rien supprimé)
  soft     : Arrêt + reset sentinelles (conserve volumes, venv, node_modules)
  standard : Arrêt + suppression volumes Docker (conserve venv, node_modules)
  full     : Suppression venv + volumes (conserve données utilisateur)
  nuclear  : Suppression totale y compris données utilisateur

.PARAMETER KeepData
  Conserve les volumes Docker (rétrocompat).

.PARAMETER FromScratch
  Supprime venv, node_modules, logs (rétrocompat).

.PARAMETER KeepDeps
  Conserve venv Python et node_modules.

.PARAMETER DeleteUserData
  Supprime data/videos et data/evidence (mode nuclear).

.PARAMETER Yes
  Mode non interactif.

.NOTES
  Requiert des droits Administrateur.
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

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. (Join-Path $PSScriptRoot 'lib\resolve-wsl-path.ps1')

function Write-Log { param([string]$Msg, [string]$Level = 'INFO')
    Write-Host "[$Level] $Msg"
}

# ── Résoudre les flags depuis --Mode ─────────────────────────────────────────
if ($Mode -eq 'restart') {
    Write-Log 'Mode restart — redémarrage des services uniquement'
    Write-Log 'Arrêt des services…'
    wsl -- bash scripts/stop-linux.sh 2>$null
    Write-Log 'Redémarrage des services…'
    wsl -- bash scripts/start-linux.sh 2>$null
    Write-Log 'Services redémarrés'
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
    ok             = $true
    windows_svc    = 'skipped'
    wsl_stop       = 'skipped'
    wsl_svc        = 'skipped'
    docker         = 'skipped'
    keep_data      = [bool]$KeepData
    keep_deps      = [bool]$KeepDeps
    delete_user_data = [bool]$DeleteUserData
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
        $wslRoot = Get-WslProjectRoot -WindowsRoot $Root
        wsl -- bash -lc "cd '$wslRoot' && docker compose -f infra/docker-compose.yml down -v" 2>$null
    }
    if ($LASTEXITCODE -eq 0) { $summary.docker = 'ok' } else { $summary.docker = 'warn' }

    Write-Log 'Suppression sentinelles…'
    $wslRoot = Get-WslProjectRoot -WindowsRoot $Root
    wsl -- bash -lc "cd '$wslRoot' && rm -f ai-engine/.venv/.installed_ok installer/.service_start_mode" 2>$null
    if ($FromScratch -and -not $KeepDeps) {
        Write-Log 'Purge from-scratch (venv, node_modules, logs)…'
        wsl -- bash -lc "cd '$wslRoot' && rm -rf ai-engine/.venv frontend/node_modules && rm -f generated.env && rm -f logs/*.log logs/*.pid && rm -rf ~/.citevision-v2 2>/dev/null || true" 2>$null
        $summary.from_scratch = 'ok'
    }
    if ($DeleteUserData) {
        Write-Log 'Suppression données utilisateur (vidéos, preuves)…'
        wsl -- bash -lc "cd '$wslRoot' && rm -rf data/videos data/evidence 2>/dev/null || true" 2>$null
        $summary.delete_user_data = 'ok'
    }
} else {
    Write-Log 'WSL non disponible — étapes Linux ignorées' 'WARN'
    if (-not $KeepData) {
        Write-Log 'Docker compose down (local)…'
        docker compose -f infra/docker-compose.yml down -v 2>$null
        if ($LASTEXITCODE -eq 0) { $summary.docker = 'ok' }
    }
}

if ($FromScratch -and -not $KeepDeps -and -not $wslOk) {
    Write-Log 'Purge from-scratch (Windows local)…'
    Remove-Item -Recurse -Force (Join-Path $Root 'ai-engine\.venv') -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $Root 'frontend\node_modules') -ErrorAction SilentlyContinue
    Remove-Item -Force (Join-Path $Root 'generated.env') -ErrorAction SilentlyContinue
    Get-ChildItem (Join-Path $Root 'logs') -Filter '*.log' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem (Join-Path $Root 'logs') -Filter '*.pid' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}
if ($DeleteUserData -and -not $wslOk) {
    Write-Log 'Suppression données utilisateur (Windows local)…'
    Remove-Item -Recurse -Force (Join-Path $Root 'data\videos') -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $Root 'data\evidence') -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Log 'Désinstallation terminée.'
Write-Log 'Pour réinstaller : lancez setup.bat'
Write-Host ''
Write-Host ($summary | ConvertTo-Json -Compress)
exit 0
