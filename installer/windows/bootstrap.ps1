#Requires -Version 5.1
<#
.SYNOPSIS
  CiteVision v2 - Windows Bootstrap Script
  Installe les prerequis manquants sur une machine Windows 11 vierge.
  Retourne JSON: {"python_ok":bool,"wsl_ok":bool,"ubuntu_ok":bool,"reboot_required":bool}

.NOTES
  Doit etre execute en tant qu'Administrateur pour activer WSL2.
  Appele automatiquement par setup.bat si necessaire.
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

# â"€â"€ VÃ©rifier admin â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]"Administrator")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# A) Python
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Log "Verification Python..."
$pythonCmds = @("python3.12","python3","python","py")
$pythonFound = $null
foreach ($cmd in $pythonCmds) {
    try {
        $v = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $v -match "Python 3\.(1[0-9]|\d{2,})") {
            $pythonFound = $cmd
            Write-Log "Python trouve: $v ($cmd)" "OK"
            break
        }
    } catch { }
}

if (-not $pythonFound) {
    Write-Log "Python absent - tentative d'installation..." "WARN"

    $installed = $false

    # MÃ©thode 1: winget
    if (-not $installed) {
        try {
            $wg = Get-Command winget -ErrorAction SilentlyContinue
            if ($wg) {
                Write-Log "Essai winget..."
                $proc = Start-Process -FilePath "winget" `
                    -ArgumentList "install","Python.Python.3.12","--silent",
                                  "--accept-package-agreements","--accept-source-agreements" `
                    -Wait -PassThru -WindowStyle Hidden
                if ($proc.ExitCode -eq 0) {
                    $installed = $true
                    Write-Log "Python installe via winget" "OK"
                } else {
                    Write-Log "winget a retourne le code $($proc.ExitCode)" "WARN"
                }
            }
        } catch { Write-Log "winget indisponible: $_" "WARN" }
    }

    # MÃ©thode 2: choco
    if (-not $installed) {
        try {
            $choco = Get-Command choco -ErrorAction SilentlyContinue
            if ($choco) {
                Write-Log "Essai Chocolatey..."
                $proc = Start-Process -FilePath "choco" `
                    -ArgumentList "install","python312","-y","--no-progress" `
                    -Wait -PassThru -WindowStyle Hidden
                if ($proc.ExitCode -eq 0) {
                    $installed = $true
                    Write-Log "Python installe via Chocolatey" "OK"
                }
            }
        } catch { Write-Log "Chocolatey indisponible: $_" "WARN" }
    }

    # MÃ©thode 3: tÃ©lÃ©chargement direct python.org
    if (-not $installed) {
        try {
            Write-Log "Telechargement Python 3.12 depuis python.org..."
            $installer_url = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"
            $tmp = "$env:TEMP\python312_setup.exe"
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            (New-Object Net.WebClient).DownloadFile($installer_url, $tmp)
            $proc = Start-Process -FilePath $tmp `
                -ArgumentList "/quiet","InstallAllUsers=1","PrependPath=1","Include_test=0" `
                -Wait -PassThru
            if ($proc.ExitCode -eq 0) {
                $installed = $true
                Write-Log "Python installe depuis python.org" "OK"
            }
            Remove-Item $tmp -ErrorAction SilentlyContinue
        } catch { Write-Log "echec telechargement python.org: $_" "ERROR" }
    }

    # RafraÃ®chir PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")

    # RevÃ©rifier
    foreach ($cmd in $pythonCmds) {
        try {
            $v = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $v -match "Python 3\.(1[0-9]|\d{2,})") {
                $pythonFound = $cmd
                Write-Log "Python maintenant disponible: $v" "OK"
                break
            }
        } catch { }
    }

    if ($installed -and -not $pythonFound) {
        # Besoin d'un redÃ©marrage de session pour le PATH
        Write-Log "Python installe mais necessite redemarrage de session pour PATH" "WARN"
        $RESULT.reboot_required = $true
    }
}

$RESULT.python_ok = ($null -ne $pythonFound)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# B) WSL2
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Log "Verification WSL2..."

$wslOk = $false
try {
    $wslStatus = & wsl --status 2>&1
    if ($LASTEXITCODE -eq 0 -and ($wslStatus -match "2" -or $wslStatus -match "Default Version: 2")) {
        $wslOk = $true
        Write-Log "WSL2 actif" "OK"
    } elseif ($LASTEXITCODE -eq 0) {
        # WSL installÃ© mais peut Ãªtre WSL1
        Write-Log "WSL present mais version incertaine: $wslStatus" "WARN"
        $wslOk = $true  # On suppose WSL2 si la commande reussit sur Win11
    }
} catch { }

if (-not $wslOk) {
    Write-Log "WSL2 absent - tentative d'activation..." "WARN"

    if (-not $isAdmin) {
        Write-Log "Droits administrateur requis pour activer WSL2 - relancement en mode admin..." "WARN"
        try {
            $ps1 = $MyInvocation.MyCommand.Path
            Start-Process powershell.exe `
                -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$ps1`"" `
                -Verb RunAs -Wait
        } catch {
            Write-Log "Impossible d'elever les droits: $_" "ERROR"
        }
    } else {
        try {
            Write-Log "Activation de la fonctionnalite WSL (sans distribution)..."
            $proc = Start-Process -FilePath "wsl" `
                -ArgumentList "--install","--no-distribution" `
                -Wait -PassThru -WindowStyle Hidden
            if ($proc.ExitCode -eq 0 -or $proc.ExitCode -eq 1) {
                Write-Log "WSL active - un redemarrage peut etre requis" "WARN"
                $RESULT.reboot_required = $true
                $wslOk = $true
            } else {
                # Essai via DISM
                Write-Log "Essai activation via DISM..."
                & dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart 2>&1 | Out-Null
                & dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart 2>&1 | Out-Null
                Write-Log "WSL active via DISM - redemarrage REQUIS" "WARN"
                $RESULT.reboot_required = $true
                $wslOk = $true
            }
            # Forcer WSL2 par dÃ©faut
            & wsl --set-default-version 2 2>&1 | Out-Null
        } catch {
            Write-Log "echec activation WSL: $_" "ERROR"
        }
    }
}

$RESULT.wsl_ok = $wslOk

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# C) Ubuntu dans WSL
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Log "Verification distribution Ubuntu dans WSL..."

$ubuntuOk = $false
if ($wslOk -and -not $RESULT.reboot_required) {
    try {
        # wsl --list retourne du UTF-16 LE : on nettoie les octets nuls avant la comparaison
        $rawList = & wsl --list 2>&1
        $cleanList = ($rawList | ForEach-Object {
            if ($_ -is [string]) { $_ -replace '\x00','' } else { [string]$_ -replace '\x00','' }
        }) -join ' '

        # Fallback : tenter wsl -l -v (table lisible)
        if (-not ($cleanList -match 'Ubuntu')) {
            $rawVerbose = & wsl -l -v 2>&1
            $cleanList  = ($rawVerbose | ForEach-Object {
                if ($_ -is [string]) { $_ -replace '\x00','' } else { [string]$_ -replace '\x00','' }
            }) -join ' '
        }

        # Fallback 2 : tenter d'exÃ©cuter bash directement pour prouver que WSL fonctionne
        if (-not ($cleanList -match 'Ubuntu')) {
            $testRc = (& wsl -- bash -c "echo ok" 2>&1)
            if ($LASTEXITCODE -eq 0 -and ($testRc -join '') -match 'ok') {
                Write-Log "WSL repond (bash ok) - distribution consideree presente" "OK"
                $cleanList = "Ubuntu" # forcer la detection
            }
        }

        if ($cleanList -match 'Ubuntu') {
            $ubuntuOk = $true
            Write-Log "Ubuntu detecte dans WSL" "OK"
        } else {
            Write-Log "Ubuntu absent - installation en cours..." "WARN"
            $proc = Start-Process -FilePath "wsl" `
                -ArgumentList "--install","Ubuntu" `
                -Wait -PassThru -WindowStyle Hidden
            if ($proc.ExitCode -eq 0) {
                $ubuntuOk = $true
                Write-Log "Ubuntu installe dans WSL" "OK"
            } else {
                $proc2 = Start-Process -FilePath "wsl" `
                    -ArgumentList "--install","-d","Ubuntu-24.04" `
                    -Wait -PassThru -WindowStyle Hidden
                if ($proc2.ExitCode -eq 0) {
                    $ubuntuOk = $true
                    Write-Log "Ubuntu 24.04 installe dans WSL" "OK"
                } else {
                    Write-Log "Installation Ubuntu a retourne code: $($proc2.ExitCode)" "WARN"
                    $RESULT.reboot_required = $true
                }
            }
        }
    } catch {
        Write-Log "Impossible de verifier les distros WSL: $_" "WARN"
    }
} elseif ($RESULT.reboot_required) {
    Write-Log "Ubuntu sera installe apres redemarrage" "INFO"
}

$RESULT.ubuntu_ok = $ubuntuOk

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Sentinel file â€" Ã©vite de refaire au prochain lancement
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
if ($RESULT.python_ok -and $RESULT.wsl_ok -and $RESULT.ubuntu_ok) {
    try {
        $sentinelDir = Split-Path $SENTINEL
        if (-not (Test-Path $sentinelDir)) { New-Item -ItemType Directory -Path $sentinelDir -Force | Out-Null }
        "Bootstrap completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Set-Content $SENTINEL -Encoding UTF8
        Write-Log "Sentinel cree: $SENTINEL" "OK"
    } catch { Write-Log "Impossible de creer le sentinel: $_" "WARN" }
}

# â"€â"€ Sortie JSON â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
$json = $RESULT | ConvertTo-Json -Compress
Write-Output $json
