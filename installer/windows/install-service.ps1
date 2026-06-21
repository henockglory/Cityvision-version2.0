#Requires -Version 5.1
<#
.SYNOPSIS
  citevision - Register / control the Windows service via NSSM.
  Auto-elevates via UAC when not admin. Downloads NSSM if missing.
  The service runs WSL under the interactive USER account (WSL distros are
  per-user, so LocalSystem cannot launch them - that caused error 1077).

.PARAMETER StartMode
  auto   - automatic startup with Windows (SERVICE_AUTO_START)
  manual - manual start via services.msc or sc start (SERVICE_DEMAND_START)

.PARAMETER Action
  register - (default) install or update the service
  start    - start the service
  stop     - stop the service

.PARAMETER Elevated
  Internal flag - set when relaunched with admin rights (prevents UAC loop).

.PARAMETER ResultFile
  Optional path to write JSON result (used when parent cannot capture elevated stdout).

.NOTES
  Returns JSON on stdout: {"service_ok":bool,"already_existed":bool,"start_mode":string,"error":string|null}
#>

param(
    [ValidateSet("auto", "manual")]
    [string]$StartMode = "auto",
    [ValidateSet("register", "start", "stop")]
    [string]$Action = "register",
    [switch]$Elevated,
    [string]$ResultFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Emit console output as UTF-8 so accented text is not garbled when the parent
# (WSL backend / installer) reads it. Guarded for headless/redirected contexts.
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { $OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

$SERVICE_NAME = "citevision"
$LEGACY_NAMES = @("CitevisionV2")
$DISPLAY_NAME = "CiteVision - AI Video Surveillance"
$NSSM_URL     = "https://nssm.cc/release/nssm-2.24.zip"
$NSSM_EXE     = "$PSScriptRoot\nssm.exe"
$ROOT         = (Resolve-Path "$PSScriptRoot\..\..").Path
$LOGS_DIR     = "$ROOT\logs"
$DEFAULT_RESULT_FILE = Join-Path $env:TEMP "citevision-svc-result.json"

function Write-Log { param([string]$msg, [string]$level = "INFO")
    Write-Host "[$level] $msg"
}

function Build-Result {
    param([bool]$ok, [bool]$existed, [string]$err = "")
    @{
        service_ok      = $ok
        already_existed = $existed
        start_mode      = $StartMode
        action          = $Action
        error           = $(if ($err) { $err } else { $null })
    }
}

function Emit-Result {
    param([bool]$ok, [bool]$existed, [string]$err = "", [int]$exitCode = 0)
    $json = (Build-Result -ok $ok -existed $existed -err $err) | ConvertTo-Json -Compress
    Write-Host $json
    $outFile = if ($ResultFile) { $ResultFile } else { $DEFAULT_RESULT_FILE }
    try {
        [System.IO.File]::WriteAllText($outFile, $json, [System.Text.UTF8Encoding]::new($false))
    } catch {
        Write-Log "Could not write result file: $_" "WARN"
    }
    exit $exitCode
}

function Set-ServiceStartMode {
    param([string]$Mode)
    if (Test-Path $NSSM_EXE) {
        $nssmStart = if ($Mode -eq "auto") { "SERVICE_AUTO_START" } else { "SERVICE_DEMAND_START" }
        & $NSSM_EXE set $SERVICE_NAME Start $nssmStart | Out-Null
        return
    }
    $scStart = if ($Mode -eq "auto") { "auto" } else { "demand" }
    & sc.exe config $SERVICE_NAME "start= $scStart" | Out-Null
}

function Test-ServiceRegistered {
    $svc = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
    if (-not $svc) { return $false }
    $scOut = & sc.exe query $SERVICE_NAME 2>&1 | Out-String
    return $scOut -match "SERVICE_NAME"
}

function Get-ServiceRunAccount {
    $qc = & sc.exe qc $SERVICE_NAME 2>&1 | Out-String
    if ($qc -match "SERVICE_START_NAME\s*:\s*(.+)") {
        return $Matches[1].Trim()
    }
    return ""
}

function Test-ServiceAccountOk {
    param([string]$Account)
    if ([string]::IsNullOrWhiteSpace($Account)) { return $false }
    $bad = @("LocalSystem", "LocalService", "NetworkService", "NT AUTHORITY\LocalService", "NT AUTHORITY\NetworkService")
    foreach ($b in $bad) {
        if ($Account -ieq $b) { return $false }
    }
    return $true
}

function Get-ServiceScState {
    $scOut = & sc.exe query $SERVICE_NAME 2>&1 | Out-String
    if ($scOut -match "STATE\s*:\s*\d+\s+(\w+)") {
        return $Matches[1].ToUpper()
    }
    return "UNKNOWN"
}

function Stop-ServiceClean {
    if (-not (Test-ServiceRegistered)) { return $true }
    Write-Log "Stopping service '$SERVICE_NAME'..."
    if (Test-Path $NSSM_EXE) {
        & $NSSM_EXE stop $SERVICE_NAME confirm 2>$null | Out-Null
    }
    & sc.exe stop $SERVICE_NAME 2>$null | Out-Null
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        $state = Get-ServiceScState
        if ($state -eq "STOPPED") {
            Write-Log "Service '$SERVICE_NAME' stopped."
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Log "Service stop timed out (state: $(Get-ServiceScState))." "WARN"
    return $false
}

function Start-ServiceRobust {
    if (-not (Test-ServiceRegistered)) {
        throw "Service '$SERVICE_NAME' is not registered"
    }
    $state = Get-ServiceScState
    if ($state -eq "RUNNING") {
        Write-Log "Service '$SERVICE_NAME' already running."
        return
    }
    if ($state -eq "PAUSED" -or $state -eq "START_PENDING" -or $state -eq "STOP_PENDING") {
        Stop-ServiceClean | Out-Null
        Start-Sleep -Seconds 2
    }
    $out = & sc.exe start $SERVICE_NAME 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        if ($out -match "1056|deja|already") {
            Write-Log "Start conflict (1056) — resetting service state..." "WARN"
            Stop-ServiceClean | Out-Null
            Start-Sleep -Seconds 2
            $out = & sc.exe start $SERVICE_NAME 2>&1 | Out-String
        }
        if ($LASTEXITCODE -ne 0) {
            throw ($out.Trim())
        }
    }
    Write-Log "Service '$SERVICE_NAME' start requested."
}

function Remove-ServiceRegistration {
    Stop-ServiceClean | Out-Null
    if (Test-Path $NSSM_EXE) {
        & $NSSM_EXE remove $SERVICE_NAME confirm 2>$null | Out-Null
    } else {
        & sc.exe delete $SERVICE_NAME 2>$null | Out-Null
    }
    Start-Sleep -Seconds 2
}

function Get-EffectiveStartMode {
    $qc = & sc.exe qc $SERVICE_NAME 2>&1 | Out-String
    if ($qc -match "AUTO_START") { return "auto" }
    if ($qc -match "DEMAND_START") { return "manual" }
    return $StartMode
}

function Test-AppRunning {
    # Backend health on 8081 means the stack is already up (installer started it).
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8081/health" -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -ge 200 -and $r.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Grant-ServiceControl {
    # Grant the given account the right to query/start/stop/reconfigure the
    # service WITHOUT admin, so the app (running in WSL as the user) can control
    # it via plain sc.exe - no UAC needed for everyday start/stop/mode changes.
    param([string]$Account)
    if ([string]::IsNullOrWhiteSpace($Account)) {
        Write-Log "Grant-ServiceControl: empty account, skipping." "WARN"
        return $false
    }
    $sid = $null
    foreach ($name in @($Account, "$env:USERDOMAIN\$Account")) {
        try {
            $sid = (New-Object System.Security.Principal.NTAccount($name)).Translate(
                [System.Security.Principal.SecurityIdentifier]).Value
            break
        } catch { }
    }
    if (-not $sid) {
        Write-Log "Could not resolve SID for '$Account' - service control not granted." "WARN"
        return $false
    }
    # SY=SYSTEM, BA=Administrators (full), <user>=control rights, IU/SU=read.
    # User rights: CC/DC/LC/SW=query+change config, RP=start, WP=stop, DT=pause,
    # LO=interrogate, CR=user-defined, RC=read control.
    $sddl = "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)" +
            "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)" +
            "(A;;CCDCLCSWRPWPDTLOCRRC;;;$sid)" +
            "(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)" +
            "S:(AU;FA;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;WD)"
    $out = & sc.exe sdset $SERVICE_NAME $sddl 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Service control granted to '$Account' (no admin needed for start/stop/mode)."
        return $true
    }
    Write-Log "sc sdset failed: $($out.Trim())" "WARN"
    return $false
}

# -- Auto-elevate via UAC if not admin --
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]"Administrator")

if (-not $isAdmin -and -not $Elevated) {
    Write-Log "Administrator rights required - requesting UAC elevation..."
    $outFile = if ($ResultFile) { $ResultFile } else { $DEFAULT_RESULT_FILE }
    if (Test-Path $outFile) { Remove-Item -Force $outFile -ErrorAction SilentlyContinue }

    # -NoLogo suppresses the PowerShell startup banner in the elevated console.
    # Do NOT add -NonInteractive here: first-time registration needs Get-Credential.
    $argList = @(
        "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-StartMode", $StartMode,
        "-Action", $Action,
        "-Elevated",
        "-ResultFile", "`"$outFile`""
    )
    try {
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList ($argList -join " ") `
            -Verb RunAs -Wait -PassThru
        if (Test-Path $outFile) {
            $content = Get-Content -Path $outFile -Raw -Encoding UTF8
            Write-Host $content.Trim()
            exit $proc.ExitCode
        }
        if ($proc.ExitCode -ne 0) {
            Emit-Result $false $false "UAC elevation failed or was denied (exit $($proc.ExitCode))" 1
        }
        Emit-Result $false $false "UAC completed but no result file found" 1
    } catch {
        Emit-Result $false $false "UAC elevation error: $_" 1
    }
}

if (-not $isAdmin) {
    Emit-Result $false $false "Administrator rights required" 1
}

# ============================================================================
#  ACTION: start / stop (no NSSM download or registration needed)
# ============================================================================
if ($Action -eq "start" -or $Action -eq "stop") {
    if (-not (Test-ServiceRegistered)) {
        Emit-Result $false $false "Service '$SERVICE_NAME' is not registered — run register-service.bat" 1
    }
    $runAs = Get-ServiceRunAccount
    if (-not (Test-ServiceAccountOk $runAs)) {
        Emit-Result $false $true "Service runs as '$runAs' (WSL incompatible) — run register-service.bat to repair" 1
    }
    try {
        if ($Action -eq "start") {
            Start-ServiceRobust
        } else {
            Stop-ServiceClean | Out-Null
        }
        Emit-Result $true $true "" 0
    } catch {
        Emit-Result $false $true "$_" 1
    }
}

# ============================================================================
#  ACTION: register (install or update)
# ============================================================================

# -- Create logs directory --
New-Item -ItemType Directory -Force -Path $LOGS_DIR | Out-Null

function Install-NssmBinary {
    if (Test-Path $NSSM_EXE) { return $true }
    $urls = @(
        $NSSM_URL,
        "https://github.com/fawno/nssm.cc/releases/download/v2.24.1/nssm-v2.24.1-Win64.zip",
        "https://github.com/fawno/nssm.cc/releases/download/v2.24.1/nssm-v2.24.1-Win32.zip"
    )
    $zipPath = "$env:TEMP\nssm-download.zip"
    $extractDir = "$env:TEMP\nssm-extract"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    foreach ($url in $urls) {
        Write-Log "Downloading NSSM from $url ..."
        try {
            if (Test-Path $zipPath) { Remove-Item -Force $zipPath -ErrorAction SilentlyContinue }
            if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
            Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing -TimeoutSec 90
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
                Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
                Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
                return $true
            }
        } catch {
            Write-Log "NSSM download failed ($url): $_" "WARN"
        }
    }
    return $false
}

# -- Remove legacy services from older builds (CitevisionV2) --
function Remove-LegacyServices {
    foreach ($legacy in $LEGACY_NAMES) {
        $svc = Get-Service -Name $legacy -ErrorAction SilentlyContinue
        if ($svc) {
            Write-Log "Removing legacy service '$legacy'..."
            try { & sc.exe stop $legacy 2>$null | Out-Null } catch {}
            if (Test-Path $NSSM_EXE) {
                & $NSSM_EXE remove $legacy confirm 2>$null | Out-Null
            } else {
                & sc.exe delete $legacy 2>$null | Out-Null
            }
        }
    }
}

# -- Resolve the user account that owns the WSL distro --
function Resolve-ServiceAccount {
    # Prefer the user who invoked the original (non-elevated) process.
    $candidate = $env:USERNAME
    try {
        $explorer = Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($explorer) {
            $owner = Invoke-CimMethod -InputObject $explorer -MethodName GetOwner -ErrorAction SilentlyContinue
            if ($owner -and $owner.User) { $candidate = $owner.User }
        }
    } catch {}
    return $candidate
}

# -- Capture and validate the Windows password for the service account --
function Get-ValidatedServiceCredential {
    param([string]$DefaultUser)
    Add-Type -AssemblyName System.DirectoryServices.AccountManagement -ErrorAction SilentlyContinue
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $cred = Get-Credential -UserName $DefaultUser `
            -Message "Mot de passe Windows pour executer le service CiteVision (compte $DefaultUser)"
        if (-not $cred) { return $null }
        $plain = $cred.GetNetworkCredential().Password
        if ([string]::IsNullOrEmpty($plain)) {
            Write-Log "Empty password not allowed for a service account." "WARN"
            continue
        }
        $userName = $cred.UserName
        if ($userName -notmatch '\\') {
            $userName = "$env:USERDOMAIN\$userName"
        }
        try {
            $ctx = New-Object System.DirectoryServices.AccountManagement.PrincipalContext('Machine')
            if ($ctx.ValidateCredentials($cred.GetNetworkCredential().UserName, $plain)) {
                return [pscustomobject]@{ Account = $userName; Password = $plain }
            }
            Write-Log "Invalid Windows credentials (attempt $attempt/3)." "WARN"
        } catch {
            # Domain account or validation unavailable: trust the input, NSSM will verify.
            return [pscustomobject]@{ Account = $userName; Password = $plain }
        }
    }
    return $null
}

# -- Convert Windows path to WSL path --
function ConvertTo-WslPath { param([string]$winPath)
    $drive = $winPath[0].ToString().ToLower()
    $rest  = $winPath.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}
$wslRoot        = ConvertTo-WslPath $ROOT
$wslStartScript = "$wslRoot/scripts/start-linux.sh"
$wslStopScript  = "$wslRoot/scripts/stop-linux.sh"

# -- Find wsl.exe --
$_wslCmd = Get-Command wsl.exe -ErrorAction SilentlyContinue
$wslExe  = if ($_wslCmd) { $_wslCmd.Source } else { "$env:SystemRoot\System32\wsl.exe" }
if (-not (Test-Path $wslExe)) {
    Emit-Result $false $false "wsl.exe not found - WSL2 required" 1
}

# -- Service already registered: repair LocalSystem installs, else update mode only --
$existingService = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if ($existingService) {
    $runAs = Get-ServiceRunAccount
    if (Test-ServiceAccountOk $runAs) {
        Write-Log "Service '$SERVICE_NAME' already registered as '$runAs' - updating mode: $StartMode"
        try {
            Set-ServiceStartMode -Mode $StartMode
            if (-not (Test-ServiceRegistered)) {
                throw "Service not visible in SCM after mode update"
            }
            Grant-ServiceControl -Account (Resolve-ServiceAccount) | Out-Null
            $effective = Get-EffectiveStartMode
            Write-Log "Start mode updated (configured: $StartMode, effective: $effective)."
            Emit-Result $true $true "" 0
        } catch {
            Emit-Result $false $true "$_" 1
        }
    }
    Write-Log "Service '$SERVICE_NAME' runs as '$runAs' (WSL incompatible) — re-registration required." "WARN"
    Remove-ServiceRegistration
}

# -- Download NSSM only when registering a new service --
if (-not (Install-NssmBinary)) {
    Emit-Result $false $false "NSSM download failed from all mirrors - place nssm.exe in installer/windows/" 1
}

Remove-LegacyServices

# -- Capture the service account credentials (required so WSL can run) --
$svcAccount = Resolve-ServiceAccount
$svcCred = Get-ValidatedServiceCredential -DefaultUser $svcAccount
if (-not $svcCred) {
    Emit-Result $false $false "Identifiants Windows requis pour executer le service (annule). Relancez register-service.bat." 1
}

# -- Register citevision service --
Write-Log "Registering Windows service '$SERVICE_NAME' (mode: $StartMode, account: $($svcCred.Account))..."

try {
    & $NSSM_EXE install $SERVICE_NAME $wslExe | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppParameters "-- bash `"$wslStartScript`"" | Out-Null

    & $NSSM_EXE set $SERVICE_NAME DisplayName $DISPLAY_NAME | Out-Null
    & $NSSM_EXE set $SERVICE_NAME Description "CiteVision intelligent video surveillance platform. Start/stop via services.msc or sc start/stop citevision." | Out-Null

    # Run as the interactive user so WSL (per-user distro) is available.
    & $NSSM_EXE set $SERVICE_NAME ObjectName $svcCred.Account $svcCred.Password | Out-Null

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
    # Do not auto-restart on crash — WSL failures as LocalSystem caused PAUSED loops.
    & $NSSM_EXE set $SERVICE_NAME AppExit Default Exit | Out-Null

    # Post-install verification with one retry
    if (-not (Test-ServiceRegistered)) {
        Write-Log "Service not found after install - retrying NSSM install..." "WARN"
        Start-Sleep -Seconds 2
        & $NSSM_EXE install $SERVICE_NAME $wslExe | Out-Null
        & $NSSM_EXE set $SERVICE_NAME ObjectName $svcCred.Account $svcCred.Password | Out-Null
        Set-ServiceStartMode -Mode $StartMode
    }
    if (-not (Test-ServiceRegistered)) {
        throw "Service '$SERVICE_NAME' not registered in SCM after install"
    }

    $runAs = Get-ServiceRunAccount
    if (-not (Test-ServiceAccountOk $runAs)) {
        throw "Service registered as '$runAs' — WSL requires a user account. Re-run register-service.bat."
    }
    Write-Log "Service account verified: $runAs"

    $effective = Get-EffectiveStartMode
    Write-Log "Service '$SERVICE_NAME' registered (configured: $StartMode, effective: $effective)."

    # Grant the user account control rights so the app can start/stop/change
    # mode later without UAC.
    Grant-ServiceControl -Account $svcCred.Account | Out-Null

    # Do not start now if the stack is already running (installer launched it).
    if ($StartMode -eq "auto") {
        Write-Log "  Automatic startup with Windows enabled."
        if (-not (Test-AppRunning)) {
            Write-Log "  Starting service now..."
            try { Start-ServiceRobust } catch { Write-Log "  Start deferred: $_" "WARN" }
        } else {
            Write-Log "  Stack already running - service will take over on next boot."
        }
    } else {
        Write-Log "  Manual mode - start via: sc start $SERVICE_NAME or services.msc"
    }
    Emit-Result $true $false "" 0
} catch {
    Write-Log "Error registering service: $_" "ERROR"
    & $NSSM_EXE remove $SERVICE_NAME confirm 2>$null
    Emit-Result $false $false "$_" 1
}
