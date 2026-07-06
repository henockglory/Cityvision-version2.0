#Requires -Version 5.1
<#
  Watchdog CitéVision (Windows) — relance la stack si le backend ne répond plus.
  Appelé par la tâche planifiée CiteVision-Watchdog (mode auto uniquement).
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

function Test-AppHealthy {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8081/health' -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch { return $false }
}

function Get-WslRoot {
    param([string]$WinRoot)
    try {
        $out = & wsl.exe wslpath -a $WinRoot 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
    } catch {}
    $drive = $WinRoot[0].ToString().ToLower()
    $rest = $WinRoot.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}

# Respect manual mode — do not restart if configured as manual
$modeFile = Join-Path $Root 'installer\.service_start_mode'
if (Test-Path $modeFile) {
    $mode = (Get-Content -Path $modeFile -Raw -Encoding UTF8).Trim().ToLower()
    if ($mode -eq 'manual') { exit 0 }
}

if (Test-AppHealthy) { exit 0 }

# Avoid concurrent restarts
if (Test-Path $lockFile) {
    $age = (Get-Date) - (Get-Item $lockFile).LastWriteTime
    if ($age.TotalMinutes -lt 8) { exit 0 }
    Remove-Item -Force $lockFile -ErrorAction SilentlyContinue
}

try {
    Set-Content -Path $lockFile -Value ([string][Environment]::TickCount) -Encoding ASCII
    Write-WdLog 'Backend down — restarting stack via start-linux.sh'
    $wslRoot = Get-WslRoot $Root
    $startScript = "$wslRoot/scripts/start-linux.sh"
    & wsl.exe -- bash -lc "cd '$wslRoot' && bash scripts/start-linux.sh" 2>&1 | Out-Null
    Start-Sleep -Seconds 5
    if (Test-AppHealthy) {
        Write-WdLog 'Restart OK'
    } else {
        Write-WdLog 'Restart attempted but backend still down'
    }
} finally {
    Remove-Item -Force $lockFile -ErrorAction SilentlyContinue
}

exit 0
