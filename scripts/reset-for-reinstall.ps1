#Requires -Version 5.1
<#
.SYNOPSIS
  Full reset to retest setup.bat.
  Keeps: AI models, venv, node_modules, Docker images.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Write-Host "=== CiteVision reset-for-reinstall ==="
Write-Host "Root: $Root"

function Stop-Remove-Service {
    param([string]$Name)
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) { return }
    Write-Host "[INFO] Stop / remove legacy service $Name..."
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
        Write-Host "  removed scheduled task $Name"
    }
}

Stop-Remove-Service 'citevision'
foreach ($legacy in @('CitevisionV2')) { Stop-Remove-Service $legacy }

Write-Host '[INFO] Removing CiteVision scheduled tasks...'
Remove-ScheduledTaskSafe 'CiteVision-AutoStart'
Remove-ScheduledTaskSafe 'CiteVision-Watchdog'

Write-Host '[INFO] Stopping WSL stack (stop-linux.sh)...'
. (Join-Path $Root 'installer\windows\Resolve-CiteVisionWslRoot.ps1')
try {
    $WslRoot = Resolve-CiteVisionWslRoot
} catch {
    Write-Host ("[WARN] {0} - skip WSL stop" -f $_.Exception.Message)
    $WslRoot = $null
}
if ($WslRoot) {
    $stopCmd = ("cd '{0}'; bash scripts/stop-linux.sh 2>/dev/null; true" -f $WslRoot)
    wsl -- bash -lc $stopCmd 2>$null
}

Write-Host '[INFO] Installer sentinels...'
@(
    'installer\.bootstrap_done',
    'installer\.service_start_mode',
    'installer\.startup_configured',
    'installer\.service_account',
    'ai-engine\.venv\.installed_ok'
) | ForEach-Object {
    $p = Join-Path $Root $_
    if (Test-Path $p) { Remove-Item -Force $p; Write-Host "  removed $_" }
}

$resultJson = Join-Path $env:TEMP 'citevision-svc-result.json'
if (Test-Path $resultJson) { Remove-Item -Force $resultJson }

Write-Host '[INFO] Reset database (users / orgs)...'
if ($WslRoot) {
    $resetCmd = ("cd '{0}'; bash scripts/reset-install-fast.sh" -f $WslRoot)
    wsl -- bash -lc $resetCmd 2>&1
} else {
    Write-Host '[WARN] WSL runtime unavailable - skip DB reset'
}

Write-Host '[INFO] Docker infra down...'
Push-Location $Root
try {
    if ($WslRoot) {
        $downCmd = ("cd '{0}'; docker compose -f infra/docker-compose.yml down 2>/dev/null; true" -f $WslRoot)
        wsl -- bash -lc $downCmd
    }
} finally { Pop-Location }

Write-Host ''
Write-Host '[OK] Ready for fresh install - run setup.bat'
Write-Host ''
