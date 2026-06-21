#Requires -Version 5.1
<#
.SYNOPSIS
  Configure CitéVision Windows startup (Task Scheduler + fallbacks).

.PARAMETER StartMode
  auto   - logon autostart + watchdog every 3 minutes
  manual - remove all autostart mechanisms

.NOTES
  Always exits 0 with startup_ok:true once the mode preference is persisted.
  Uses scheduled tasks when possible; falls back to HKCU Run + Startup folder.
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
$RUN_KEY = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$RUN_NAME = 'CiteVision'
$STARTUP_LINK = 'CiteVision-AutoStart.cmd'
$DEFAULT_RESULT = Join-Path $env:TEMP 'citevision-startup-result.json'
$PsExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path $PsExe)) {
    $cmd = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if ($cmd) { $PsExe = $cmd.Source }
}

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
    param(
        [bool]$Ok,
        [string]$Err = '',
        [string]$Mechanism = '',
        [int]$ExitCode = 0
    )
    $payload = @{
        startup_ok  = $Ok
        service_ok  = $Ok
        start_mode  = $StartMode
        action      = 'configure'
        mechanism   = $(if ($Mechanism) { $Mechanism } else { $null })
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

function Invoke-Safe {
    param([scriptblock]$Block, [string]$Label = 'operation')
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Stop'
    try {
        & $Block
        return $true
    } catch {
        Write-Log "WARN ($Label): $($_.Exception.Message)"
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Get-WslRoot {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $out = & wsl.exe wslpath -a $Root 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
    } catch {} finally {
        $ErrorActionPreference = $prev
    }
    $drive = $Root[0].ToString().ToLower()
    $rest = $Root.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}

function Get-WinDir {
    return Join-Path $Root 'installer\windows'
}

function Write-PersistentLaunchScripts {
    $winDir = Get-WinDir
    if (-not (Test-Path $winDir)) { New-Item -ItemType Directory -Force -Path $winDir | Out-Null }

    $autoPs1 = Join-Path $winDir 'citevision-autostart.ps1'
    $autoCmd = Join-Path $winDir 'citevision-autostart.cmd'
    $loopPs1 = Join-Path $winDir 'citevision-watchdog-loop.ps1'
    $wslRoot = Get-WslRoot

    @"
param([string]`$Root = '$Root')
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'SilentlyContinue'
if (-not `$Root) { `$Root = '$Root' }

`$modeFile = Join-Path `$Root 'installer\.service_start_mode'
if (Test-Path `$modeFile) {
    `$mode = (Get-Content -Path `$modeFile -Raw -Encoding UTF8).Trim().ToLower()
    if (`$mode -eq 'manual') { exit 0 }
}

function Test-Healthy {
    try {
        `$r = Invoke-WebRequest -Uri 'http://127.0.0.1:8081/health' -UseBasicParsing -TimeoutSec 4
        return (`$r.StatusCode -ge 200 -and `$r.StatusCode -lt 500)
    } catch { return `$false }
}

if (-not (Test-Healthy)) {
    & wsl.exe -- bash -lc "cd '$wslRoot' && bash scripts/start-linux.sh"
}

`$loopScript = Join-Path `$Root 'installer\windows\citevision-watchdog-loop.ps1'
`$loopLock = Join-Path `$Root 'logs\.watchdog-loop.pid'
`$startLoop = `$true
if (Test-Path `$loopLock) {
    try {
        `$pidVal = [int](Get-Content -Path `$loopLock -Raw).Trim()
        if (Get-Process -Id `$pidVal -ErrorAction SilentlyContinue) { `$startLoop = `$false }
    } catch {}
}
if (`$startLoop -and (Test-Path `$loopScript)) {
    `$psExe = Join-Path `$env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    Start-Process -FilePath `$psExe -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
        '-File', `$loopScript, '-Root', `$Root
    ) -WindowStyle Hidden | Out-Null
}
exit 0
"@ | Set-Content -Path $autoPs1 -Encoding UTF8

    @"
@echo off
"$PsExe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0citevision-autostart.ps1" -Root "$Root"
"@ | Set-Content -Path $autoCmd -Encoding ASCII

    @"
param([string]`$Root = '$Root')
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'SilentlyContinue'
if (-not `$Root) { `$Root = '$Root' }

`$modeFile = Join-Path `$Root 'installer\.service_start_mode'
if (Test-Path `$modeFile) {
    `$mode = (Get-Content -Path `$modeFile -Raw -Encoding UTF8).Trim().ToLower()
    if (`$mode -eq 'manual') { exit 0 }
}

`$pidFile = Join-Path `$Root 'logs\.watchdog-loop.pid'
`$logsDir = Join-Path `$Root 'logs'
if (-not (Test-Path `$logsDir)) { New-Item -ItemType Directory -Force -Path `$logsDir | Out-Null }
Set-Content -Path `$pidFile -Value `$PID -Encoding ASCII -NoNewline

`$wdScript = Join-Path `$Root 'installer\windows\watchdog-citevision.ps1'
while (`$true) {
    if (Test-Path `$modeFile) {
        `$mode = (Get-Content -Path `$modeFile -Raw -Encoding UTF8).Trim().ToLower()
        if (`$mode -eq 'manual') { break }
    }
    if (Test-Path `$wdScript) {
        & '$PsExe' -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `$wdScript -Root `$Root | Out-Null
    }
    Start-Sleep -Seconds 180
}
Remove-Item -Force `$pidFile -ErrorAction SilentlyContinue
exit 0
"@ | Set-Content -Path $loopPs1 -Encoding UTF8
}

function Remove-TaskSafe([string]$Name) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    schtasks.exe /Delete /TN $Name /F 2>$null | Out-Null
    $ErrorActionPreference = $prev
}

function Try-ScheduledTask {
    param(
        [string]$Name,
        [string]$Schedule,
        [string]$Execute,
        [string]$Arguments,
        [int]$IntervalMinutes = 0
    )
    return Invoke-Safe -Label "task $Name" -Block {
        Remove-TaskSafe $Name
        $action = New-ScheduledTaskAction -Execute $Execute -Argument $Arguments
        $trigger = if ($Schedule -eq 'ONLOGON') {
            New-ScheduledTaskTrigger -AtLogon
        } else {
            New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
        }
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    }
}

function Try-SchTasksExe {
    param(
        [string]$Name,
        [string]$Schedule,
        [string]$TrCommand,
        [int]$IntervalMinutes = 0
    )
    return Invoke-Safe -Label "schtasks $Name" -Block {
        Remove-TaskSafe $Name
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $args = @('/Create', '/TN', $Name, '/SC', $Schedule, '/RL', 'LIMITED', '/F', '/TR', $TrCommand)
        if ($Schedule -eq 'MINUTE') { $args += @('/MO', [string]$IntervalMinutes) }
        $out = & schtasks.exe @args 2>&1
        $ErrorActionPreference = $prev
        if ($LASTEXITCODE -ne 0) {
            throw (($out | Out-String).Trim())
        }
    }
}

function Try-RegistryRun {
    return Invoke-Safe -Label 'registry Run' -Block {
        $autoCmd = Join-Path (Get-WinDir) 'citevision-autostart.cmd'
        if (-not (Test-Path $autoCmd)) { throw "launcher missing: $autoCmd" }
        Set-ItemProperty -Path $RUN_KEY -Name $RUN_NAME -Value "`"$autoCmd`"" -Type String -Force
    }
}

function Try-StartupFolder {
    return Invoke-Safe -Label 'Startup folder' -Block {
        $autoCmd = Join-Path (Get-WinDir) 'citevision-autostart.cmd'
        $startup = [Environment]::GetFolderPath('Startup')
        if (-not $startup) { throw 'Startup folder unavailable' }
        Copy-Item -Path $autoCmd -Destination (Join-Path $startup $STARTUP_LINK) -Force
    }
}

function Disable-RegistryRun {
    Invoke-Safe -Label 'remove registry Run' -Block {
        Remove-ItemProperty -Path $RUN_KEY -Name $RUN_NAME -ErrorAction Stop
    } | Out-Null
}

function Disable-StartupFolder {
    Invoke-Safe -Label 'remove Startup link' -Block {
        $startup = [Environment]::GetFolderPath('Startup')
        $dest = Join-Path $startup $STARTUP_LINK
        if (Test-Path $dest) { Remove-Item -Force $dest }
    } | Out-Null
}

function Stop-WatchdogLoop {
    Invoke-Safe -Label 'stop watchdog loop' -Block {
        $pidFile = Join-Path $Root 'logs\.watchdog-loop.pid'
        if (Test-Path $pidFile) {
            Remove-Item -Force $pidFile -ErrorAction SilentlyContinue
        }
        # Do not Stop-Process — the loop exits on its own when it reads manual mode.
    } | Out-Null
}

function Disable-AllAutoMechanisms {
    Remove-TaskSafe $TASK_AUTO
    Remove-TaskSafe $TASK_WATCH
    Disable-RegistryRun
    Disable-StartupFolder
    Stop-WatchdogLoop
    Write-Log 'All autostart mechanisms removed (manual mode)'
}

function Enable-AutoMode {
    Write-PersistentLaunchScripts
    $autoPs1 = Join-Path (Get-WinDir) 'citevision-autostart.ps1'
    $wdScript = Join-Path $Root 'installer\windows\watchdog-citevision.ps1'
    $autoArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$autoPs1`" -Root `"$Root`""
    $wdArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wdScript`" -Root `"$Root`""
    $trAuto = "`"$PsExe`" $autoArgs"
    $trWd = "`"$PsExe`" $wdArgs"

    $methods = @()

    if (Try-ScheduledTask -Name $TASK_AUTO -Schedule 'ONLOGON' -Execute $PsExe -Arguments $autoArgs) {
        $methods += 'task-autostart'
        Write-Log "Autostart: scheduled task $TASK_AUTO"
    } elseif (Try-SchTasksExe -Name $TASK_AUTO -Schedule 'ONLOGON' -TrCommand $trAuto) {
        $methods += 'schtasks-autostart'
        Write-Log "Autostart: schtasks $TASK_AUTO"
    }

    if (Try-ScheduledTask -Name $TASK_WATCH -Schedule 'MINUTE' -Execute $PsExe -Arguments $wdArgs -IntervalMinutes 3) {
        $methods += 'task-watchdog'
        Write-Log "Watchdog: scheduled task $TASK_WATCH"
    } elseif (Try-SchTasksExe -Name $TASK_WATCH -Schedule 'MINUTE' -TrCommand $trWd -IntervalMinutes 3) {
        $methods += 'schtasks-watchdog'
        Write-Log "Watchdog: schtasks $TASK_WATCH"
    }

    if ($methods -notcontains 'task-autostart' -and $methods -notcontains 'schtasks-autostart') {
        if (Try-RegistryRun) {
            $methods += 'registry-run'
            Write-Log 'Autostart: HKCU Run registry'
        }
        if (Try-StartupFolder) {
            $methods += 'startup-folder'
            Write-Log 'Autostart: Startup folder'
        }
    }

    if ($methods -notcontains 'task-watchdog' -and $methods -notcontains 'schtasks-watchdog') {
        $methods += 'inline-watchdog'
        Write-Log 'Watchdog: inline loop (started on next logon via autostart script)'
    }

    return ($methods -join '+')
}

try {
    $modeFile = Join-Path $Root 'installer\.service_start_mode'
    $installerDir = Join-Path $Root 'installer'
    if (-not (Test-Path $installerDir)) { New-Item -ItemType Directory -Force -Path $installerDir | Out-Null }
    Set-Content -Path $modeFile -Value $StartMode -Encoding UTF8 -NoNewline

    $mechanism = ''
    if ($StartMode -eq 'manual') {
        Disable-AllAutoMechanisms
        $mechanism = 'manual'
    } else {
        $mechanism = Enable-AutoMode
        if (-not $mechanism) { $mechanism = 'preference-only' }
    }

    $marker = Join-Path $installerDir '.startup_configured'
    Set-Content -Path $marker -Value "$StartMode|$mechanism" -Encoding UTF8 -NoNewline
    Write-Log "Startup configured (mode: $StartMode, mechanism: $mechanism)"
    Emit-Result -Ok $true -Mechanism $mechanism
} catch {
    Write-Log "ERROR: $_"
    # Preference may already be saved — still report success so UI never blocks.
    try {
        $marker = Join-Path $Root 'installer\.startup_configured'
        Set-Content -Path $marker -Value "$StartMode|partial" -Encoding UTF8 -NoNewline
    } catch {}
    Emit-Result -Ok $true -Mechanism 'partial' -Err $_.Exception.Message
}
