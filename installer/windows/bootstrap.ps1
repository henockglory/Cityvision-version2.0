#Requires -Version 5.1
<#
.SYNOPSIS
  CiteVision v2 - Windows Bootstrap Script
  Installs missing prerequisites on a clean Windows 11 machine.
  Returns JSON: {"python_ok":bool,"wsl_ok":bool,"ubuntu_ok":bool,"reboot_required":bool}

.NOTES
  Run as Administrator to enable WSL2.
  Called automatically by setup.bat when needed.
  Runtime stack: WSL ~/citevision-v2 only (never /mnt/c mirrors). Use launcher\Start-CiteVision.ps1.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ROOT       = (Resolve-Path "$PSScriptRoot\..\.." ).Path
$SENTINEL   = "$ROOT\installer\.bootstrap_done"
$RESULT     = @{ python_ok = $false; wsl_ok = $false; ubuntu_ok = $false; reboot_required = $false }

function Write-Log { param([string]$msg, [string]$level = "INFO")
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts][$level] $msg"
}

function ConvertTo-WslMirrorPath {
    param([string]$winPath)
    $drive = $winPath[0].ToString().ToLower()
    $rest  = $winPath.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}

# --- Admin check ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]"Administrator")

# --- A) Python ---
Write-Log "Checking Python..."
$pythonCmds = @("python3.12","python3","python","py")
$pythonFound = $null
foreach ($cmd in $pythonCmds) {
    try {
        $v = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $v -match "Python 3\.(1[0-9]|\d{2,})") {
            $pythonFound = $cmd
            Write-Log "Python found: $v ($cmd)" "OK"
            break
        }
    } catch { }
}

if (-not $pythonFound) {
    Write-Log "Python missing - attempting install..." "WARN"

    $installed = $false

    if (-not $installed) {
        try {
            $wg = Get-Command winget -ErrorAction SilentlyContinue
            if ($wg) {
                Write-Log "Trying winget..."
                $proc = Start-Process -FilePath "winget" `
                    -ArgumentList "install","Python.Python.3.12","--silent",
                                  "--accept-package-agreements","--accept-source-agreements" `
                    -Wait -PassThru -WindowStyle Hidden
                if ($proc.ExitCode -eq 0) {
                    $installed = $true
                    Write-Log "Python installed via winget" "OK"
                } else {
                    Write-Log "winget returned exit code $($proc.ExitCode)" "WARN"
                }
            }
        } catch { Write-Log "winget unavailable: $_" "WARN" }
    }

    if (-not $installed) {
        try {
            $choco = Get-Command choco -ErrorAction SilentlyContinue
            if ($choco) {
                Write-Log "Trying Chocolatey..."
                $proc = Start-Process -FilePath "choco" `
                    -ArgumentList "install","python312","-y","--no-progress" `
                    -Wait -PassThru -WindowStyle Hidden
                if ($proc.ExitCode -eq 0) {
                    $installed = $true
                    Write-Log "Python installed via Chocolatey" "OK"
                }
            }
        } catch { Write-Log "Chocolatey unavailable: $_" "WARN" }
    }

    if (-not $installed) {
        try {
            Write-Log "Downloading Python 3.12 from python.org..."
            $installer_url = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"
            $tmp = "$env:TEMP\python312_setup.exe"
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            (New-Object Net.WebClient).DownloadFile($installer_url, $tmp)
            $proc = Start-Process -FilePath $tmp `
                -ArgumentList "/quiet","InstallAllUsers=1","PrependPath=1","Include_test=0" `
                -Wait -PassThru
            if ($proc.ExitCode -eq 0) {
                $installed = $true
                Write-Log "Python installed from python.org" "OK"
            }
            Remove-Item $tmp -ErrorAction SilentlyContinue
        } catch { Write-Log "python.org download failed: $_" "ERROR" }
    }

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")

    foreach ($cmd in $pythonCmds) {
        try {
            $v = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $v -match "Python 3\.(1[0-9]|\d{2,})") {
                $pythonFound = $cmd
                Write-Log "Python now available: $v" "OK"
                break
            }
        } catch { }
    }

    if ($installed -and -not $pythonFound) {
        Write-Log "Python installed but session restart may be needed for PATH" "WARN"
        $RESULT.reboot_required = $true
    }
}

$RESULT.python_ok = ($null -ne $pythonFound)

# --- B) WSL2 ---
Write-Log "Checking WSL2..."

$wslOk = $false
try {
    $wslStatus = & wsl --status 2>&1
    if ($LASTEXITCODE -eq 0 -and ($wslStatus -match "2" -or $wslStatus -match "Default Version: 2")) {
        $wslOk = $true
        Write-Log "WSL2 active" "OK"
    } elseif ($LASTEXITCODE -eq 0) {
        Write-Log "WSL present but version uncertain: $wslStatus" "WARN"
        $wslOk = $true
    }
} catch { }

if (-not $wslOk) {
    Write-Log "WSL2 missing - attempting enable..." "WARN"

    if (-not $isAdmin) {
        Write-Log "Administrator rights required for WSL2 - relaunching elevated..." "WARN"
        try {
            $ps1 = $MyInvocation.MyCommand.Path
            Start-Process powershell.exe `
                -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$ps1`"" `
                -Verb RunAs -Wait
        } catch {
            Write-Log "Could not elevate: $_" "ERROR"
        }
    } else {
        try {
            Write-Log "Enabling WSL feature (no distribution)..."
            $proc = Start-Process -FilePath "wsl" `
                -ArgumentList "--install","--no-distribution" `
                -Wait -PassThru -WindowStyle Hidden
            if ($proc.ExitCode -eq 0 -or $proc.ExitCode -eq 1) {
                Write-Log "WSL enabled - reboot may be required" "WARN"
                $RESULT.reboot_required = $true
                $wslOk = $true
            } else {
                Write-Log "Trying DISM enable..."
                & dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart 2>&1 | Out-Null
                & dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart 2>&1 | Out-Null
                Write-Log "WSL enabled via DISM - reboot REQUIRED" "WARN"
                $RESULT.reboot_required = $true
                $wslOk = $true
            }
            & wsl --set-default-version 2 2>&1 | Out-Null
        } catch {
            Write-Log "WSL enable failed: $_" "ERROR"
        }
    }
}

$RESULT.wsl_ok = $wslOk

# --- C) Ubuntu in WSL ---
Write-Log "Checking Ubuntu WSL distribution..."

$ubuntuOk = $false
if ($wslOk -and -not $RESULT.reboot_required) {
    try {
        $rawList = & wsl --list 2>&1
        $cleanList = ($rawList | ForEach-Object {
            if ($_ -is [string]) { $_ -replace '\x00','' } else { [string]$_ -replace '\x00','' }
        }) -join ' '

        if (-not ($cleanList -match 'Ubuntu')) {
            $rawVerbose = & wsl -l -v 2>&1
            $cleanList  = ($rawVerbose | ForEach-Object {
                if ($_ -is [string]) { $_ -replace '\x00','' } else { [string]$_ -replace '\x00','' }
            }) -join ' '
        }

        if (-not ($cleanList -match 'Ubuntu')) {
            $testRc = (& wsl -- bash -c "echo ok" 2>&1)
            if ($LASTEXITCODE -eq 0 -and ($testRc -join '') -match 'ok') {
                Write-Log "WSL responds (bash ok) - treating distribution as present" "OK"
                $cleanList = "Ubuntu"
            }
        }

        if ($cleanList -match 'Ubuntu') {
            $ubuntuOk = $true
            Write-Log "Ubuntu detected in WSL" "OK"
        } else {
            Write-Log "Ubuntu missing - installing..." "WARN"
            $proc = Start-Process -FilePath "wsl" `
                -ArgumentList "--install","Ubuntu" `
                -Wait -PassThru -WindowStyle Hidden
            if ($proc.ExitCode -eq 0) {
                $ubuntuOk = $true
                Write-Log "Ubuntu installed in WSL" "OK"
            } else {
                $proc2 = Start-Process -FilePath "wsl" `
                    -ArgumentList "--install","-d","Ubuntu-24.04" `
                    -Wait -PassThru -WindowStyle Hidden
                if ($proc2.ExitCode -eq 0) {
                    $ubuntuOk = $true
                    Write-Log "Ubuntu 24.04 installed in WSL" "OK"
                } else {
                    Write-Log "Ubuntu install returned code: $($proc2.ExitCode)" "WARN"
                    $RESULT.reboot_required = $true
                }
            }
        }
    } catch {
        Write-Log "Could not verify WSL distros: $_" "WARN"
    }
} elseif ($RESULT.reboot_required) {
    Write-Log "Ubuntu will be installed after reboot" "INFO"
}

$RESULT.ubuntu_ok = $ubuntuOk

# --- D) Native WSL runtime (~/citevision-v2) ---
if ($wslOk -and $ubuntuOk -and -not $RESULT.reboot_required) {
    Write-Log "Checking native WSL runtime..."
    $runtimeProbe = 'test -f "$HOME/citevision-v2/scripts/start-linux.sh"'
    & wsl.exe -- bash -lc $runtimeProbe 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Native runtime missing - syncing from Windows mirror..." "WARN"
        $mirrorWsl = ConvertTo-WslMirrorPath $ROOT
        $syncSh = "$mirrorWsl/scripts/sync-to-wsl.sh"
        $syncCmd = ("bash '{0}' '{1}'" -f $syncSh, $mirrorWsl)
        & wsl.exe -- bash -lc $syncCmd
        if ($LASTEXITCODE -ne 0) {
            Write-Log "sync-to-wsl.sh failed (exit $LASTEXITCODE)" "WARN"
        } else {
            Write-Log "Native runtime synced from Windows mirror" "OK"
        }
        & wsl.exe -- bash -lc $runtimeProbe 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & wsl.exe -- bash -lc 'touch "$HOME/citevision-v2/.wsl_runtime_ready"' 2>$null | Out-Null
            Write-Log "Wrote .wsl_runtime_ready in native root" "OK"
        } else {
            Write-Log "Runtime still missing after sync - run scripts/sync-to-wsl.sh manually" "WARN"
        }
    } else {
        Write-Log "Native runtime present" "OK"
        & wsl.exe -- bash -lc 'touch "$HOME/citevision-v2/.wsl_runtime_ready"' 2>$null | Out-Null
    }
}

# --- Sentinel file ---
if ($RESULT.python_ok -and $RESULT.wsl_ok -and $RESULT.ubuntu_ok) {
    try {
        $sentinelDir = Split-Path $SENTINEL
        if (-not (Test-Path $sentinelDir)) { New-Item -ItemType Directory -Path $sentinelDir -Force | Out-Null }
        "Bootstrap completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Set-Content $SENTINEL -Encoding UTF8
        Write-Log "Sentinel created: $SENTINEL" "OK"
    } catch { Write-Log "Could not create sentinel: $_" "WARN" }
}

# --- JSON output ---
$json = $RESULT | ConvertTo-Json -Compress
Write-Output $json
