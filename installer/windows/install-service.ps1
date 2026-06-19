#Requires -Version 5.1
<#
.SYNOPSIS
  CitéVision v2 — Enregistrement du service Windows via NSSM.
  Télécharge NSSM si absent, puis enregistre le service "CitéVision"
  qui démarre start-linux.sh dans WSL et s'arrête proprement via stop-linux.sh.

.PARAMETER StartMode
  auto   — démarrage automatique avec Windows (SERVICE_AUTO_START)
  manual — démarrage manuel via services.msc ou sc start (SERVICE_DEMAND_START)

.NOTES
  Requiert des droits Administrateur.
  Appelé par install_stream() après setup-wsl.sh.
  Retourne JSON : {"service_ok": bool, "already_existed": bool, "start_mode": string, "error": string|null}
#>

param(
    [ValidateSet("auto", "manual")]
    [string]$StartMode = "auto"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SERVICE_NAME = "CitéVision"
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

# ── Vérifier admin ────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]"Administrator")
if (-not $isAdmin) {
    Write-Log "Droits administrateur requis pour enregistrer un service Windows." "WARN"
    Out-Result $false $false "Droits administrateur requis"
    exit 1
}

# ── Créer répertoire logs ─────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $LOGS_DIR | Out-Null

# ── Télécharger NSSM si absent ────────────────────────────────────────────────
if (-not (Test-Path $NSSM_EXE)) {
    Write-Log "Téléchargement de NSSM..."
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
            Write-Log "NSSM téléchargé : $NSSM_EXE"
        } else {
            throw "nssm.exe non trouvé dans l'archive"
        }
        Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
        Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
    } catch {
        Write-Log "Téléchargement NSSM échoué : $_" "ERROR"
        Out-Result $false $false "Téléchargement NSSM échoué : $_"
        exit 1
    }
}

# ── Convertir chemin Windows → WSL ───────────────────────────────────────────
function ConvertTo-WslPath { param([string]$winPath)
    $drive  = $winPath[0].ToString().ToLower()
    $rest   = $winPath.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}
$wslRoot        = ConvertTo-WslPath $ROOT
$wslStartScript = "$wslRoot/scripts/start-linux.sh"
$wslStopScript  = "$wslRoot/scripts/stop-linux.sh"

# ── wsl.exe ───────────────────────────────────────────────────────────────────
$wslExe = (Get-Command wsl.exe -ErrorAction SilentlyContinue)?.Source
if (-not $wslExe) { $wslExe = "$env:SystemRoot\System32\wsl.exe" }
if (-not (Test-Path $wslExe)) {
    Write-Log "wsl.exe introuvable — WSL2 requis." "ERROR"
    Out-Result $false $false "wsl.exe introuvable"
    exit 1
}

# ── Service déjà enregistré → mettre à jour le mode de démarrage ─────────────
$existingService = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Log "Service '$SERVICE_NAME' déjà enregistré — mise à jour mode: $StartMode"
    try {
        Set-ServiceStartMode -Mode $StartMode
        Write-Log "Mode de démarrage mis à jour ($StartMode)."
        Out-Result $true $true
        exit 0
    } catch {
        Write-Log "Erreur mise à jour mode : $_" "ERROR"
        Out-Result $false $true "$_"
        exit 1
    }
}

# ── Enregistrer le service CitéVision ────────────────────────────────────────
Write-Log "Enregistrement du service Windows '$SERVICE_NAME' (mode: $StartMode)..."

try {
    & $NSSM_EXE install $SERVICE_NAME $wslExe | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppParameters "-- bash `"$wslStartScript`"" | Out-Null

    & $NSSM_EXE set $SERVICE_NAME DisplayName "CitéVision — Surveillance IA" | Out-Null
    & $NSSM_EXE set $SERVICE_NAME Description "Plateforme d'analyse vidéo intelligente CitéVision v2. Démarrez/arrêtez via services.msc ou sc start/stop CitéVision." | Out-Null

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

    Write-Log "Service '$SERVICE_NAME' enregistré avec succès (mode: $StartMode)."
    if ($StartMode -eq "auto") {
        Write-Log "  Démarrage automatique avec Windows activé."
    } else {
        Write-Log "  Mode manuel — démarrer via: sc start `"$SERVICE_NAME`" ou services.msc"
    }
    Out-Result $true $false
    exit 0
} catch {
    Write-Log "Erreur lors de l'enregistrement du service : $_" "ERROR"
    & $NSSM_EXE remove $SERVICE_NAME confirm 2>$null
    Out-Result $false $false "$_"
    exit 1
}
