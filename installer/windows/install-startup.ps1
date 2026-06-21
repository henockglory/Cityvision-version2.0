#Requires -Version 5.1
<#
.SYNOPSIS
  Configure CitéVision Windows startup via Task Scheduler (no services.msc / NSSM).

.PARAMETER StartMode
  auto   - logon task + watchdog every 3 minutes
  manual - remove/disable scheduled tasks

.PARAMETER Root
  Project root (Windows path).

.PARAMETER ResultFile
  Optional JSON result path for callers (installer / backend).

.NOTES
  Emits JSON on stdout: {"startup_ok":bool,"start_mode":string,"error":string|null}
#>
param(
    [ValidateSet('auto', 'manual')]
    [string]$StartMode = 'auto',
    [string]$Root = '',
    [string]$ResultFile = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TASK_AUTO = 'CiteVision-AutoStart'
$TASK_WATCH = 'CiteVision-Watchdog'
$DEFAULT_RESULT = Join-Path $env:TEMP 'citevision-startup-result.json'

if (-not $Root) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
$Root = $Root.TrimEnd('\')

function Write-Log([string]$Msg) {
    $logsDir = Join-Path $Root 'logs'
    if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Force -Path $logsDir | Out-Null }
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $Msg"
    try { Add-Content -Path (Join-Path $logsDir 'install-startup.log') -Value $line -Encoding UTF8 } catch {}
    Write-Host $line
}

function Emit-Result {
    param([bool]$Ok, [string]$Err = '', [int]$ExitCode = 0)
    $payload = @{
        startup_ok  = $Ok
        service_ok  = $Ok   # backward compat for deps-checker parser
        start_mode  = $StartMode
        action      = 'configure'
        error       = $(if ($Err) { $Err } else { $null })
    }
    $json = $payload | ConvertTo-Json -Compress
    Write-Host $json
    $out = if ($ResultFile) { $ResultFile } else { $DEFAULT_RESULT }
    try {
        [System.IO.File]::WriteAllText($out, $json, [System.Text.UTF8Encoding]::new($false))
    } catch {}
    exit $ExitCode
}

function Get-WslRoot {
    try {
        $out = & wsl.exe wslpath -a $Root 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
    } catch {}
    $drive = $Root[0].ToString().ToLower()
    $rest = $Root.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}

function Remove-TaskSafe([string]$Name) {
    schtasks.exe /Delete /TN $Name /F 2>$null | Out-Null
}

function Test-TaskExists([string]$Name) {
    $null = schtasks.exe /Query /TN $Name 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Test-AppHealthy {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8081/health' -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch { return $false }
}

function Register-AutoStartTask {
    $wslRoot = Get-WslRoot
    $startScript = "$wslRoot/scripts/start-linux.sh"
    # Wrapper: skip if already healthy
    $psWrapper = Join-Path $env:TEMP 'citevision-autostart.ps1'
    @"
`$ErrorActionPreference = 'SilentlyContinue'
try {
  `$r = Invoke-WebRequest -Uri 'http://127.0.0.1:8081/health' -UseBasicParsing -TimeoutSec 4
  if (`$r.StatusCode -ge 200 -and `$r.StatusCode -lt 500) { exit 0 }
} catch {}
& wsl.exe -- bash -lc "cd '$wslRoot' && bash scripts/start-linux.sh"
"@ | Set-Content -Path $psWrapper -Encoding UTF8

    Remove-TaskSafe $TASK_AUTO
    $tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$psWrapper`""
    schtasks.exe /Create /TN $TASK_AUTO /SC ONLOGON /RL LIMITED /F /TR $tr | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks create $TASK_AUTO failed (exit $LASTEXITCODE)"
    }
    Write-Log "Task $TASK_AUTO registered (ONLOGON)"
}

function Register-WatchdogTask {
    $wdScript = Join-Path $Root 'installer\windows\watchdog-citevision.ps1'
    if (-not (Test-Path $wdScript)) {
        throw "Watchdog script missing: $wdScript"
    }
    Remove-TaskSafe $TASK_WATCH
    $tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wdScript`" -Root `"$Root`""
    schtasks.exe /Create /TN $TASK_WATCH /SC MINUTE /MO 3 /RL LIMITED /F /TR $tr | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks create $TASK_WATCH failed (exit $LASTEXITCODE)"
    }
    Write-Log "Task $TASK_WATCH registered (every 3 min)"
}

function Disable-AutoTasks {
    Remove-TaskSafe $TASK_AUTO
    Remove-TaskSafe $TASK_WATCH
    Write-Log 'Scheduled tasks removed (manual mode)'
}

try {
    $modeFile = Join-Path $Root 'installer\.service_start_mode'
    $installerDir = Join-Path $Root 'installer'
    if (-not (Test-Path $installerDir)) { New-Item -ItemType Directory -Force -Path $installerDir | Out-Null }
    Set-Content -Path $modeFile -Value $StartMode -Encoding UTF8 -NoNewline

    if ($StartMode -eq 'auto') {
        Register-AutoStartTask
        Register-WatchdogTask
    } else {
        Disable-AutoTasks
    }

    $marker = Join-Path $installerDir '.startup_configured'
    Set-Content -Path $marker -Value $StartMode -Encoding UTF8 -NoNewline
    Write-Log "Startup configured (mode: $StartMode)"
    Emit-Result -Ok $true
} catch {
    Write-Log "ERROR: $_"
    Emit-Result -Ok $false -Err $_.Exception.Message -ExitCode 1
}
