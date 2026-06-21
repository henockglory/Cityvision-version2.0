#Requires -Version 5.1
<#
.SYNOPSIS
  Remise à zéro complète pour retester setup.bat.
  Conserve : modèles IA, venv, node_modules, images Docker.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Write-Host "=== CitéVision reset-for-reinstall ==="
Write-Host "Root: $Root"

function Stop-Remove-Service {
    param([string]$Name)
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) { return }
    Write-Host "[INFO] Arrêt / suppression service legacy $Name..."
    sc.exe stop $Name 2>$null | Out-Null
    Start-Sleep -Seconds 2
    $nssm = Join-Path $Root 'installer\windows\nssm.exe'
    if (Test-Path $nssm) {
        & $nssm remove $Name confirm 2>$null | Out-Null
    }
    sc.exe delete $Name 2>$null | Out-Null
    Start-Sleep -Seconds 1
}

function Remove-ScheduledTaskSafe {
    param([string]$Name)
    schtasks.exe /Delete /TN $Name /F 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  tâche supprimée $Name"
    }
}

Stop-Remove-Service 'citevision'
foreach ($legacy in @('CitevisionV2')) { Stop-Remove-Service $legacy }

Write-Host '[INFO] Suppression tâches planifiées CitéVision...'
Remove-ScheduledTaskSafe 'CiteVision-AutoStart'
Remove-ScheduledTaskSafe 'CiteVision-Watchdog'

Write-Host '[INFO] Arrêt stack WSL (stop-linux.sh)...'
$drive = $Root.Substring(0, 1).ToLower()
$rest = $Root.Substring(2).Replace('\', '/')
$wslRoot = "/mnt/$drive$rest"
wsl -- bash -lc "cd '$wslRoot' && bash scripts/stop-linux.sh 2>/dev/null || true" 2>$null

Write-Host '[INFO] Sentinels installateur...'
@(
    'installer\.bootstrap_done',
    'installer\.service_start_mode',
    'installer\.startup_configured',
    'installer\.service_account',
    'ai-engine\.venv\.installed_ok'
) | ForEach-Object {
    $p = Join-Path $Root $_
    if (Test-Path $p) { Remove-Item -Force $p; Write-Host "  supprimé $_" }
}

$resultJson = Join-Path $env:TEMP 'citevision-svc-result.json'
if (Test-Path $resultJson) { Remove-Item -Force $resultJson }

Write-Host '[INFO] Remise à zéro base de données (utilisateurs / orgs)…'
wsl -- bash -lc "cd '$wslRoot' && bash scripts/reset-install-fast.sh" 2>&1

Write-Host '[INFO] Docker infra down...'
Push-Location $Root
try {
    wsl -- bash -lc "cd '$wslRoot' && docker compose -f infra/docker-compose.yml down 2>/dev/null || true"
} finally { Pop-Location }

Write-Host ''
Write-Host '[OK] Prêt pour une nouvelle installation — lancez setup.bat'
Write-Host ''
