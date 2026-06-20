#Requires -Version 5.1
<#
.SYNOPSIS
  CitevisionV2 - Register Windows service via NSSM.
  Downloads NSSM if missing, then registers the CitevisionV2 service
  which starts start-linux.sh in WSL and stops cleanly via stop-linux.sh.

.PARAMETER StartMode
  auto   - automatic startup with Windows (SERVICE_AUTO_START)
  manual - manual start via services.msc or sc start (SERVICE_DEMAND_START)

.NOTES
  Requires Administrator rights.
  Called by install_stream() after setup-wsl.sh.
  Returns JSON: {"service_ok": bool, "already_existed": bool, "start_mode": string, "error": string|null}
#>

param(
    [ValidateSet("auto", "manual")]
    [string]$StartMode = "auto"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SERVICE_NAME = "CitevisionV2"
$NSSM_URL     = "https://nssm.cc/release/nssm-2.24.zip"
$NSSM_EXE     = "$PSScriptRoot\nssm.exe"
$ROOT         = (Resolve-Path "$PSScriptRoot\..\..").Path
$LOGS_DIR     = "$ROOT\logs"

function Write-Log { param([string]$msg, [string]$level = "INFO")
    Write-Host "[$level] $msg"
}

function Out-Result {
    param([bool]$ok, [bool]$existed, [string]$err = "")
    @{
        service_ok      = $ok
        already_existed = $existed
        start_mode      = $StartMode
        error           = $(if ($err) { $err } else { $null })
    } | ConvertTo-Json -Compress
}

function Set-ServiceStartMode {
    param([string]$Mode)
    $nssmStart = if ($Mode -eq "auto") { "SERVICE_AUTO_START" } else { "SERVICE_DEMAND_START" }
    & $NSSM_EXE set $SERVICE_NAME Start $nssmStart | Out-Null
}

# -- Check admin --
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]"Administrator")
if (-not $isAdmin) {
    Write-Log "Administrator rights required to register a Windows service." "WARN"
    Out-Result $false $false "Administrator rights required"
    exit 1
}

# -- Create logs directory --
New-Item -ItemType Directory -Force -Path $LOGS_DIR | Out-Null

# -- Download NSSM if missing --
if (-not (Test-Path $NSSM_EXE)) {
    Write-Log "Downloading NSSM..."
    $zipPath = "$env:TEMP\nssm-2.24.zip"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $NSSM_URL -OutFile $zipPath -UseBasicParsing -TimeoutSec 30
        $extractDir = "$env:TEMP\nssm-extract"
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
        $nssmBin = Get-ChildItem -Path $extractDir -Recurse -Filter "nssm.exe" |
            Where-Object { $_.FullName -match "win64" } |
            Select-Object -First 1
        if (-not $nssmBin) {
            $nssmBin = Get-ChildItem -Path $extractDir -Recurse -Filter "nssm.exe" |
                Select-Object -First 1
        }
        if ($nssmBin) {
            Copy-Item -Path $nssmBin.FullName -Destination $NSSM_EXE -Force
            Write-Log "NSSM downloaded: $NSSM_EXE"
        } else {
            throw "nssm.exe not found in archive"
        }
        Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
        Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
    } catch {
        Write-Log "NSSM download failed: $_" "ERROR"
        Out-Result $false $false "NSSM download failed: $_"
        exit 1
    }
}

# -- Convert Windows path to WSL path --
function ConvertTo-WslPath { param([string]$winPath)
    $drive  = $winPath[0].ToString().ToLower()
    $rest   = $winPath.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}
$wslRoot        = ConvertTo-WslPath $ROOT
$wslStartScript = "$wslRoot/scripts/start-linux.sh"
$wslStopScript  = "$wslRoot/scripts/stop-linux.sh"

# -- Find wsl.exe --
$_wslCmd = Get-Command wsl.exe -ErrorAction SilentlyContinue
$wslExe  = if ($_wslCmd) { $_wslCmd.Source } else { "$env:SystemRoot\System32\wsl.exe" }
if (-not (Test-Path $wslExe)) {
    Write-Log "wsl.exe not found - WSL2 required." "ERROR"
    Out-Result $false $false "wsl.exe not found"
    exit 1
}

# -- Service already registered: update start mode only --
$existingService = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Log "Service '$SERVICE_NAME' already registered - updating mode: $StartMode"
    try {
        Set-ServiceStartMode -Mode $StartMode
        Write-Log "Start mode updated ($StartMode)."
        Out-Result $true $true
        exit 0
    } catch {
        Write-Log "Error updating start mode: $_" "ERROR"
        Out-Result $false $true "$_"
        exit 1
    }
}

# -- Register CitevisionV2 service --
Write-Log "Registering Windows service '$SERVICE_NAME' (mode: $StartMode)..."

try {
    & $NSSM_EXE install $SERVICE_NAME $wslExe | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppParameters "-- bash `"$wslStartScript`"" | Out-Null

    & $NSSM_EXE set $SERVICE_NAME DisplayName "CitevisionV2 - AI Video Surveillance" | Out-Null
    & $NSSM_EXE set $SERVICE_NAME Description "CitevisionV2 intelligent video surveillance platform. Start/stop via services.msc or sc start/stop CitevisionV2." | Out-Null

    Set-ServiceStartMode -Mode $StartMode

    & $NSSM_EXE set $SERVICE_NAME AppDirectory $ROOT | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppStdout "$LOGS_DIR\service.log" | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppStderr "$LOGS_DIR\service-error.log" | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppRotateFiles 1 | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppRotateBytes 5242880 | Out-Null

    & $NSSM_EXE set $SERVICE_NAME AppStopMethodSkip 6 | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppStopMethodConsole 5000 | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppStopMethodWindow 5000 | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppStopMethodThreads 5000 | Out-Null

    & $NSSM_EXE set $SERVICE_NAME AppEvents "Stop/Pre" "`"$wslExe`" -- bash `"$wslStopScript`"" | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppRestartDelay 10000 | Out-Null

    Write-Log "Service '$SERVICE_NAME' registered successfully (mode: $StartMode)."
    if ($StartMode -eq "auto") {
        Write-Log "  Automatic startup with Windows enabled."
    } else {
        Write-Log "  Manual mode - start via: sc start `"$SERVICE_NAME`" or services.msc"
    }
    Out-Result $true $false
    exit 0
} catch {
    Write-Log "Error registering service: $_" "ERROR"
    & $NSSM_EXE remove $SERVICE_NAME confirm 2>$null
    Out-Result $false $false "$_"
    exit 1
}
