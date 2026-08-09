# Apply balanced WSL2 resource profile for CiteVision + Cursor coexistence.
# Keeps enough RAM/CPU for Frigate+AI demos while leaving headroom for Windows/Cursor.
# Run: powershell -ExecutionPolicy Bypass -File scripts/apply-wsl-balanced-resources.ps1
# Then: wsl --shutdown  (reopens on next wsl.exe)
$ErrorActionPreference = 'Stop'
$cfg = Join-Path $env:USERPROFILE '.wslconfig'
$content = @"
# CiteVision - balanced (i9-13900H / 64GB host)
# Applied by scripts/apply-wsl-balanced-resources.ps1
# Demos/smoke/AI CUDA still fit; Cursor/Windows keep ~40GB headroom.
[wsl2]
memory=20GB
processors=14
swap=8GB
localhostForwarding=true
"@
Set-Content -Path $cfg -Value $content -Encoding utf8
Write-Host "Wrote $cfg"
Write-Host "Apply with: wsl --shutdown   (then reopen WSL / Cursor Remote)"
Get-Content $cfg
