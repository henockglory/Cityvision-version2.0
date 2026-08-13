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
# 20GB: CUDA AI + Frigate + UI; 12GB OOM-killed Vite repeatedly (product UI is now static).
memory=20GB
processors=8
swap=8GB
localhostForwarding=true
"@
# UTF-8 no BOM — BOM broke some parsers / made Start miss memory= lines.
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($cfg, ($content -replace "`r`n", "`n").Trim() + "`n", $utf8NoBom)
Write-Host "Wrote $cfg"
Write-Host "Apply with: wsl --shutdown   (then reopen WSL / Cursor Remote)"
Get-Content $cfg
