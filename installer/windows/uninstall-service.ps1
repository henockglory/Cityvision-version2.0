#Requires -Version 5.1
<#
.SYNOPSIS
  citevision - Remove Windows service.
  Stops the service cleanly then removes it from the Windows registry.

.NOTES
  Requires Administrator rights.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

# Emit console output as UTF-8 so accented text is not garbled upstream.
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { $OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

# Find all Citevision-related services (handles both old accented and new ASCII names)
$SERVICE_NAMES = @(Get-Service | Where-Object { $_.Name -like "Cit*" -and $_.Name -match "(?i)vision" } | Select-Object -ExpandProperty Name)
if ($SERVICE_NAMES.Count -eq 0) { $SERVICE_NAMES = @("citevision", "CitevisionV2") }
$NSSM_EXE      = "$PSScriptRoot\nssm.exe"

function Write-Log { param([string]$msg, [string]$level = "INFO")
    Write-Host "[$level] $msg"
}

# -- Check admin --
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]"Administrator")
if (-not $isAdmin) {
    Write-Log "Administrator rights required." "ERROR"
    exit 1
}

$removed = 0
foreach ($SERVICE_NAME in $SERVICE_NAMES) {
    $svc = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
    if (-not $svc) { continue }

    Write-Log "Found service: $SERVICE_NAME"

    # -- Stop if running --
    if ($svc.Status -eq "Running") {
        Write-Log "Stopping service '$SERVICE_NAME'..."
        if (Test-Path $NSSM_EXE) {
            & $NSSM_EXE stop $SERVICE_NAME confirm | Out-Null
        } else {
            Stop-Service -Name $SERVICE_NAME -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 5
    }

    # -- Remove service --
    Write-Log "Removing service '$SERVICE_NAME'..."
    if (Test-Path $NSSM_EXE) {
        & $NSSM_EXE remove $SERVICE_NAME confirm | Out-Null
    } else {
        sc.exe delete $SERVICE_NAME | Out-Null
    }

    $svcAfter = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
    if (-not $svcAfter) {
        Write-Log "Service '$SERVICE_NAME' removed successfully."
        $removed++
    } else {
        Write-Log "Service '$SERVICE_NAME' removal incomplete - restart Windows if needed." "WARN"
    }
}

if ($removed -eq 0) {
    Write-Log "No citevision service found - nothing to remove."
}
exit 0
