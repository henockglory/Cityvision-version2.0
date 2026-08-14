#Requires -Version 5.1
<#
  Watchdog CiteVision (Windows) - heals backend / Frigate / AI when stack is down.
  Called by scheduled task CiteVision-Watchdog (auto mode only).
  ASCII-only for Windows PowerShell 5.1.

  Important: WSL localhostForwarding can publish a port on ::1 only (not 127.0.0.1).
  Never treat "Windows 127.0.0.1 unreachable" as API-down if WSL curl succeeds —
  a destructive start-linux would kill in-flight work (demo ffmpeg transcode, etc.).
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

# Prefer IPv4, fall back to IPv6 (::1) — wslrelay sometimes binds only one family.
function Test-WinPortHealthy([int]$Port, [string]$Path) {
    if (Test-UrlHealthy ("http://127.0.0.1:{0}{1}" -f $Port, $Path)) { return $true }
    if (Test-UrlHealthy ("http://[::1]:{0}{1}" -f $Port, $Path)) { return $true }
    return $false
}

function Test-WslUrlHealthy([string]$Url) {
    & wsl.exe -- bash -lc ("curl -sf --max-time 3 '{0}' >/dev/null 2>&1" -f $Url) | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Invoke-WslRelaySoftWake {
    # Touch listeners from inside WSL so wslrelay may re-advertise IPv4 localhost.
    & wsl.exe -- bash -lc @'
curl -sf --max-time 2 http://127.0.0.1:8081/health >/dev/null 2>&1 || true
curl -sf --max-time 2 http://127.0.0.1:8001/health >/dev/null 2>&1 || true
curl -sf --max-time 2 http://127.0.0.1:5000/api/version >/dev/null 2>&1 || true
curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null 2>&1 || true
'@ | Out-Null
}

function Get-StackHealth {
    $apiWin = Test-WinPortHealthy 8081 '/health'
    $aiWin = Test-WinPortHealthy 8001 '/health'
    $frigateWin = Test-WinPortHealthy 5000 '/api/version'

    $apiWsl = $false
    $aiWsl = $false
    $frigateWsl = $false
    if (-not ($apiWin -and $aiWin -and $frigateWin)) {
        $apiWsl = Test-WslUrlHealthy 'http://127.0.0.1:8081/health'
        $aiWsl = Test-WslUrlHealthy 'http://127.0.0.1:8001/health'
        $frigateWsl = Test-WslUrlHealthy 'http://127.0.0.1:5000/api/version'
    } else {
        $apiWsl = $true
        $aiWsl = $true
        $frigateWsl = $true
    }

    $apiOk = ($apiWin -or $apiWsl)
    $aiOk = ($aiWin -or $aiWsl)
    $frigateOk = ($frigateWin -or $frigateWsl)

    return @{
        ApiWin     = $apiWin
        AiWin      = $aiWin
        FrigateWin = $frigateWin
        ApiWsl     = $apiWsl
        AiWsl      = $aiWsl
        FrigateWsl = $frigateWsl
        Api        = $apiOk
        Ai         = $aiOk
        Frigate    = $frigateOk
        All        = ($apiOk -and $aiOk -and $frigateOk)
        WinAll     = ($apiWin -and $aiWin -and $frigateWin)
        RelayGap   = ($apiOk -and $aiOk -and $frigateOk -and -not ($apiWin -and $aiWin -and $frigateWin))
    }
}

$resolverPath = Join-Path $Root 'installer\windows\Resolve-CiteVisionWslRoot.ps1'

# Respect manual mode - do not restart if configured as manual
$modeFile = Join-Path $Root 'installer\.service_start_mode'
if (Test-Path $modeFile) {
    $mode = (Get-Content -Path $modeFile -Raw -Encoding UTF8).Trim().ToLower()
    if ($mode -eq 'manual') { exit 0 }
}

$health = Get-StackHealth
if ($health.WinAll) { exit 0 }

# Stack is fine inside WSL; Windows localhost path is partial/broken.
# Soft-wake the relay and do NOT run start-linux (would kill API + demo transcodes).
if ($health.All -and $health.RelayGap) {
    Write-WdLog ("Relay gap apiWin={0} aiWin={1} frigateWin={2} (WSL ok) - soft-wake, skip start-linux" -f $health.ApiWin, $health.AiWin, $health.FrigateWin)
    Invoke-WslRelaySoftWake
    exit 0
}

if ($health.All) { exit 0 }

# Avoid concurrent restarts
if (Test-Path $lockFile) {
    $age = (Get-Date) - (Get-Item $lockFile).LastWriteTime
    if ($age.TotalMinutes -lt 8) { exit 0 }
    Remove-Item -Force $lockFile -ErrorAction SilentlyContinue
}

try {
    Set-Content -Path $lockFile -Value ([string][Environment]::TickCount) -Encoding ASCII
    Write-WdLog ("Stack degraded api={0}(win={1}/wsl={2}) ai={3}(win={4}/wsl={5}) frigate={6}(win={7}/wsl={8})" -f `
        $health.Api, $health.ApiWin, $health.ApiWsl, `
        $health.Ai, $health.AiWin, $health.AiWsl, `
        $health.Frigate, $health.FrigateWin, $health.FrigateWsl)
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

    # Full start-linux ONLY when API is actually down inside WSL.
    if (-not $health.Api) {
        $bashCmd = ("cd '{0}'; bash scripts/start-linux.sh" -f $wslRoot)
        Write-WdLog 'Backend down in WSL - start-linux.sh'
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
        Write-WdLog 'API up in WSL - targeted Frigate/AI/infra heal (no API restart)'
    }
    & wsl.exe -- bash -lc $bashCmd 2>&1 | Out-Null
    Start-Sleep -Seconds 8
    $after = Get-StackHealth
    if ($after.WinAll) {
        Write-WdLog 'Heal OK (Windows localhost api+ai+frigate)'
    } elseif ($after.All) {
        Write-WdLog ("Heal OK in WSL; Windows still partial apiWin={0} aiWin={1} frigateWin={2}" -f $after.ApiWin, $after.AiWin, $after.FrigateWin)
        Invoke-WslRelaySoftWake
    } elseif ($after.Api) {
        Write-WdLog ("Heal partial api=ok ai={0} frigate={1}" -f $after.Ai, $after.Frigate)
    } else {
        Write-WdLog 'Heal attempted but backend still down in WSL'
    }
} finally {
    Remove-Item -Force $lockFile -ErrorAction SilentlyContinue
}

exit 0
