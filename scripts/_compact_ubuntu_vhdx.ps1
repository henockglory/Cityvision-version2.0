# 1) sparse off  2) diskpart compact  3) sparse on --allow-unsafe
$ErrorActionPreference = "Continue"
$log = "C:\Users\gheno\citevision\scripts\compact-log.txt"
$vhdx = "C:\Users\gheno\AppData\Local\wsl\{c5515942-ee60-4c07-8acf-bef2540fe7e1}\ext4.vhdx"
function Log($m){ $line = "$m"; Write-Host $line; Add-Content -Path $log -Value $line -Encoding utf8 }

Set-Content $log "START $(Get-Date -Format o)" -Encoding utf8
Log "C free: $([math]::Round((Get-PSDrive C).Free/1GB,2)) GB"
Log "VHDX: $([math]::Round((Get-Item -LiteralPath $vhdx).Length/1GB,2)) GB"

Log "shutdown WSL"
wsl --shutdown
Start-Sleep 10
Stop-Process -Name wsl,wslhost,wslservice -Force -ErrorAction SilentlyContinue
Start-Sleep 5

Log "set-sparse false"
$r1 = wsl --manage Ubuntu-24.04 --set-sparse false 2>&1 | Out-String
Log $r1
Start-Sleep 3

Log "diskpart compact"
$dp = "$env:TEMP\cv_compact.txt"
@"
select vdisk file="$vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@ | Set-Content $dp -Encoding ASCII
$out = "$env:TEMP\cv_compact_out.txt"
$p = Start-Process diskpart -ArgumentList "/s `"$dp`"" -Wait -PassThru -NoNewWindow -RedirectStandardOutput $out
Log (Get-Content $out -Raw -ErrorAction SilentlyContinue)
Log "exit=$($p.ExitCode) VHDX=$([math]::Round((Get-Item -LiteralPath $vhdx).Length/1GB,2))GB"

Log "set-sparse true --allow-unsafe"
$r2 = wsl --manage Ubuntu-24.04 --set-sparse true --allow-unsafe 2>&1 | Out-String
Log $r2

Log "C free: $([math]::Round((Get-PSDrive C).Free/1GB,2)) GB"
Log "DONE"
