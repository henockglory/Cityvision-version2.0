# Run as Administrator BEFORE rebooting
# Enables Windows features required for WSL2
#Requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'

Write-Host "=== Enable WSL2 prerequisites (Windows) ==="
Write-Host ""

Write-Host "[1/3] Enabling Virtual Machine Platform..."
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

Write-Host "[2/3] Enabling Windows Subsystem for Linux..."
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart

Write-Host "[3/3] Setting WSL2 as default..."
wsl --set-default-version 2

Write-Host ""
Write-Host "=== NEXT STEPS (manual) ==="
Write-Host "1. Reboot BIOS/UEFI and enable Intel VT-x or AMD-V"
Write-Host "2. Reboot Windows"
Write-Host "3. Run: wsl -d Ubuntu-24.04"
Write-Host "4. In WSL: bash scripts/sync-to-wsl.sh && bash scripts/setup-wsl.sh && bash scripts/start-linux.sh"
Write-Host ""
Write-Host "Guide: docs/WSL-MIGRATION.md"
