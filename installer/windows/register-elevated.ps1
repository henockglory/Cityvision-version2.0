#Requires -Version 5.1
<#
  Invoked only by register-service.bat (entry point for Windows service registration).
  Opens a visible PowerShell window, requests UAC once, runs install-service.ps1.
#>
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [string]$StartMode = "auto",
    [Parameter(Mandatory = $true)][string]$LogFile,
    [Parameter(Mandatory = $true)][string]$ResultFile,
    [switch]$Silent,
    [switch]$Handover
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

$logDir = Split-Path -Parent $LogFile
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }

try { Start-Transcript -Path $LogFile -Append -Force | Out-Null } catch {}

function Write-Step([string]$Msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $Msg"
    Write-Host $line
}

$ps1 = Join-Path $Root "installer\windows\install-service.ps1"
if (-not (Test-Path $ps1)) {
    Write-Step "ERROR: install-service.ps1 not found: $ps1"
    exit 1
}

$innerArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ps1,
    "-StartMode", $StartMode,
    "-Elevated",
    "-ResultFile", $ResultFile
)
if ($Handover) { $innerArgs += "-Handover" }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Step "CiteVision - enregistrement du service Windows (mode: $StartMode)"
Write-Step "Log: $LogFile"

$exitCode = 1
try {
    if ($isAdmin) {
        Write-Step "Running as Administrator..."
        & powershell.exe @innerArgs *>&1 | Tee-Object -FilePath $LogFile -Append
        $exitCode = $LASTEXITCODE
    } else {
        Write-Step "UAC elevation required - accept the prompt..."
        try {
            Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
            [void][System.Windows.Forms.MessageBox]::Show(
                "CiteVision va demander les droits administrateur (UAC)." + [Environment]::NewLine + [Environment]::NewLine +
                "1. Cliquez Oui sur UAC" + [Environment]::NewLine +
                "2. Saisissez le mot de passe de votre compte Microsoft (PAS le PIN)",
                "CiteVision - Enregistrement du service",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Warning
            )
        } catch {}
        # RunAs cannot be combined with -RedirectStandardOutput/-RedirectStandardError (PS 5.1).
        # install-service.ps1 writes to logs/register-service-install.log independently.
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $innerArgs `
            -Verb RunAs -Wait -PassThru
        $exitCode = if ($null -ne $proc -and $null -ne $proc.ExitCode) { $proc.ExitCode } else { 1 }
    }
} catch {
    Write-Step "ERROR: $_"
    $exitCode = 1
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}

if ($exitCode -eq 0) {
    Write-Step "OK: Service citevision registered."
} else {
    Write-Step "FAILED: exit code $exitCode"
    if (Test-Path $ResultFile) {
        try {
            Write-Step (Get-Content -Path $ResultFile -Raw -Encoding UTF8).Trim()
        } catch {}
    }
    if (-not $Silent) {
        Write-Host ""
        Read-Host "Appuyez sur Entree pour fermer"
    }
}

exit $exitCode
