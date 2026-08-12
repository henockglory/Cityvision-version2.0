# Apply Cursor-first WSL2 resource profile (CiteVision Frigate on GPU + Windows headroom).
# Run: powershell -ExecutionPolicy Bypass -File scripts/apply-wsl-balanced-resources.ps1
# Then: wsl --shutdown
$ErrorActionPreference = 'Stop'
$cfg = Join-Path $env:USERPROFILE '.wslconfig'
$content = @"
# CiteVision - Cursor-first (i9-13900H / 64GB host)
# Applied by scripts/apply-wsl-balanced-resources.ps1
# Frigate detector on GPU (stable-tensorrt); Cursor/Windows keep headroom.
[wsl2]
memory=12GB
processors=8
swap=4GB
localhostForwarding=true
"@
Set-Content -Path $cfg -Value $content -Encoding utf8
Write-Host "Wrote $cfg"
Write-Host "Apply with: wsl --shutdown   (then reopen WSL / Cursor Remote)"
Get-Content $cfg
