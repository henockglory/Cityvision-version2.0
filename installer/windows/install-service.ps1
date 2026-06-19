#Requires -Version 5.1
<#
.SYNOPSIS
  CitéVision v2 — Enregistrement du service Windows via NSSM.
  Télécharge NSSM si absent, puis enregistre le service "CitéVision"
  qui démarre start-linux.sh dans WSL et s'arrête proprement via stop-linux.sh.

.NOTES
  Requiert des droits Administrateur.
  Appelé automatiquement par setup.bat.
  Retourne JSON sur stdout : {"service_ok": bool, "already_existed": bool, "error": string|null}
#>

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

function Out-Result { param([bool]$ok, [bool]$existed, [string]$err = "")
    @{ service_ok = $ok; already_existed = $existed; error = $err } | ConvertTo-Json -Compress
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
        # L'archive contient nssm-2.24/win64/nssm.exe
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
$wslRoot      = ConvertTo-WslPath $ROOT
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

# ── Vérifier si service déjà enregistré ──────────────────────────────────────
$existingService = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Log "Service '$SERVICE_NAME' déjà enregistré (état : $($existingService.Status))."
    Out-Result $true $true
    exit 0
}

# ── Enregistrer le service CitéVision ────────────────────────────────────────
Write-Log "Enregistrement du service Windows '$SERVICE_NAME'..."

try {
    # Installation principale : wsl.exe "-- bash <start-linux.sh>"
    & $NSSM_EXE install $SERVICE_NAME $wslExe | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppParameters "-- bash `"$wslStartScript`"" | Out-Null

    # Métadonnées
    & $NSSM_EXE set $SERVICE_NAME DisplayName "CitéVision — Surveillance IA" | Out-Null
    & $NSSM_EXE set $SERVICE_NAME Description "Plateforme d'analyse vidéo intelligente CitéVision v2. Démarrez/arrêtez via ce panneau ou via setup.bat." | Out-Null

    # Démarrage automatique avec Windows
    & $NSSM_EXE set $SERVICE_NAME Start SERVICE_AUTO_START | Out-Null

    # Répertoire de travail
    & $NSSM_EXE set $SERVICE_NAME AppDirectory $ROOT | Out-Null

    # Logs service
    & $NSSM_EXE set $SERVICE_NAME AppStdout "$LOGS_DIR\service.log" | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppStderr "$LOGS_DIR\service-error.log" | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppRotateFiles 1 | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppRotateBytes 5242880 | Out-Null  # 5 Mo

    # Arrêt propre : délais avant kill, pour laisser stop-linux.sh s'exécuter
    & $NSSM_EXE set $SERVICE_NAME AppStopMethodSkip 6 | Out-Null       # skip Ctrl+C direct
    & $NSSM_EXE set $SERVICE_NAME AppStopMethodConsole 5000 | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppStopMethodWindow 5000 | Out-Null
    & $NSSM_EXE set $SERVICE_NAME AppStopMethodThreads 5000 | Out-Null

    # Pré-stop : exécuter stop-linux.sh avant que NSSM tue le processus
    & $NSSM_EXE set $SERVICE_NAME AppEvents "Stop/Pre" "`"$wslExe`" -- bash `"$wslStopScript`"" | Out-Null

    # Redémarrage automatique en cas de crash (délai 10s)
    & $NSSM_EXE set $SERVICE_NAME AppRestartDelay 10000 | Out-Null

    Write-Log "Service '$SERVICE_NAME' enregistré avec succès."
    Write-Log "  Démarrage : sc start `"$SERVICE_NAME`"  ou via services.msc"
    Write-Log "  Arrêt    : sc stop  `"$SERVICE_NAME`"  ou via services.msc"
    Out-Result $true $false
    exit 0
} catch {
    Write-Log "Erreur lors de l'enregistrement du service : $_" "ERROR"
    # Nettoyage en cas d'échec partiel
    & $NSSM_EXE remove $SERVICE_NAME confirm 2>$null
    Out-Result $false $false "$_"
    exit 1
}
