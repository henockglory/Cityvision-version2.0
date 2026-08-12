#Requires -Version 5.1
<#
  Watchdog CiteVision (Windows) - heals backend / Frigate / AI when stack is down.
  Called by scheduled task CiteVision-Watchdog (auto mode only).
  ASCII-only for Windows PowerShell 5.1.
  Aligns with Start-CiteVision / ensure_infra_host_ports + start-linux heal path.
#>
param(
    [Parameter(Mandatory = $true)][string]$Root
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'

$logsDir = Join-Path $Root 'logs'
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Force -Path $logsDir | Out-Null }

$lockFile = Join-Path $logsDir '.watchdog.lock'
$logFile  = Join-Path $logsDir 'watchdog.log'

function Write-WdLog([string]$Msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg"
    try { Add-Content -Path $logFile -Value $line -Encoding UTF8 } catch {}
}

function Test-UrlHealthy([string]$Uri) {
    try {
        $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch { return $false }
}

function Test-StackHealthy {
    $apiOk = Test-UrlHealthy 'http://127.0.0.1:8081/health'
    $aiOk = Test-UrlHealthy 'http://127.0.0.1:8001/health'
    $frigateOk = Test-UrlHealthy 'http://127.0.0.1:5000/api/version'
    return @{
        Api     = $apiOk
        Ai      = $aiOk
        Frigate = $frigateOk
        All     = ($apiOk -and $aiOk -and $frigateOk)
    }
}

$resolverPath = Join-Path $Root 'installer\windows\Resolve-CiteVisionWslRoot.ps1'

# Respect manual mode - do not restart if configured as manual
$modeFile = Join-Path $Root 'installer\.service_start_mode'
if (Test-Path $modeFile) {
    $mode = (Get-Content -Path $modeFile -Raw -Encoding UTF8).Trim().ToLower()
    if ($mode -eq 'manual') { exit 0 }
}

$health = Test-StackHealthy
if ($health.All) { exit 0 }

# Avoid concurrent restarts
if (Test-Path $lockFile) {
    $age = (Get-Date) - (Get-Item $lockFile).LastWriteTime
    if ($age.TotalMinutes -lt 8) { exit 0 }
    Remove-Item -Force $lockFile -ErrorAction SilentlyContinue
}

try {
    Set-Content -Path $lockFile -Value ([string][Environment]::TickCount) -Encoding ASCII
    Write-WdLog ("Stack degraded api={0} ai={1} frigate={2} - healing via start-linux + infra ports" -f $health.Api, $health.Ai, $health.Frigate)
    . $resolverPath
    try {
        $wslRoot = Resolve-CiteVisionWslRoot
    } catch {
        Write-WdLog ("FAIL: {0}" -f $_.Exception.Message)
        exit 1
    }
    if ($wslRoot -match '^/mnt/') {
        Write-WdLog 'FAIL: runtime under /mnt/* refused'
        exit 1
    }

    # Prefer targeted heal when only infra/AI is down; full start-linux if API is down.
    if (-not $health.Api) {
        $bashCmd = ("cd '{0}'; bash scripts/start-linux.sh" -f $wslRoot)
        Write-WdLog 'Backend down - start-linux.sh'
    } else {
        $bashCmd = @"
cd '$wslRoot'
set -uo pipefail
source scripts/lib/service-heal.sh 2>/dev/null || true
source scripts/lib/business-readiness.sh 2>/dev/null || true
declare -F ensure_infra_host_ports >/dev/null 2>&1 && ensure_infra_host_ports || true
declare -F ensure_business_readiness >/dev/null 2>&1 && ensure_business_readiness || true
if [[ -f scripts/ensure-ai-stack.sh ]]; then
  bash scripts/ensure-ai-stack.sh --fix --max-attempts=2 || true
fi
if [[ -f scripts/frigate_watchdog.sh ]]; then
  WATCH_FRIGATE_LOOP=0 bash scripts/frigate_watchdog.sh || true
fi
"@
        Write-WdLog 'API up - targeted Frigate/AI/infra heal'
    }
    & wsl.exe -- bash -lc $bashCmd 2>&1 | Out-Null
    Start-Sleep -Seconds 8
    $after = Test-StackHealthy
    if ($after.All) {
        Write-WdLog 'Heal OK (api+ai+frigate)'
    } elseif ($after.Api) {
        Write-WdLog ("Heal partial api=ok ai={0} frigate={1}" -f $after.Ai, $after.Frigate)
    } else {
        Write-WdLog 'Heal attempted but backend still down'
    }
} finally {
    Remove-Item -Force $lockFile -ErrorAction SilentlyContinue
}

exit 0
