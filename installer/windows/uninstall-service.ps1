#Requires -Version 5.1
<#
.SYNOPSIS
  CitéVision v2 — Suppression du service Windows CitéVision.
  Arrête le service proprement puis le supprime du registre Windows.

.NOTES
  Requiert des droits Administrateur.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

$SERVICE_NAME = "CitéVision"
$NSSM_EXE     = "$PSScriptRoot\nssm.exe"

function Write-Log { param([string]$msg, [string]$level = "INFO")
    Write-Host "[$level] $msg"
}

# ── Vérifier admin ────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]"Administrator")
if (-not $isAdmin) {
    Write-Log "Droits administrateur requis." "ERROR"
    exit 1
}

# ── Vérifier que le service existe ───────────────────────────────────────────
$svc = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Log "Service '$SERVICE_NAME' non trouvé — rien à supprimer."
    exit 0
}

# ── Arrêter le service si en cours ───────────────────────────────────────────
if ($svc.Status -eq "Running") {
    Write-Log "Arrêt du service '$SERVICE_NAME'..."
    if (Test-Path $NSSM_EXE) {
        & $NSSM_EXE stop $SERVICE_NAME confirm | Out-Null
    } else {
        Stop-Service -Name $SERVICE_NAME -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 5
}

# ── Supprimer le service ──────────────────────────────────────────────────────
Write-Log "Suppression du service '$SERVICE_NAME'..."
if (Test-Path $NSSM_EXE) {
    & $NSSM_EXE remove $SERVICE_NAME confirm | Out-Null
} else {
    sc.exe delete $SERVICE_NAME | Out-Null
}

$svcAfter = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if (-not $svcAfter) {
    Write-Log "Service '$SERVICE_NAME' supprimé avec succès."
    exit 0
} else {
    Write-Log "Suppression incomplète — redémarrez Windows et relancez." "WARN"
    exit 1
}
