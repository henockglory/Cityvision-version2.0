# Must run as admin
$vhdx = "C:\Users\gheno\AppData\Local\wsl\{c5515942-ee60-4c07-8acf-bef2540fe7e1}\ext4.vhdx"
$log  = "C:\Users\gheno\citevision\scripts\_compact_now2.log"

"[$(Get-Date)] START" | Out-File $log
"VHDX before: $([math]::Round((Get-Item $vhdx).Length/1GB,1)) GB" | Tee-Object -Append $log

# Shut down WSL and wait until the lock is released
wsl.exe --shutdown
Start-Sleep -Seconds 25

$diskpartScript = @"
select vdisk file="$vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
$tmpScript = "$env:TEMP\cv_compact2.txt"
$diskpartScript | Out-File -Encoding ascii $tmpScript

"Running diskpart..." | Tee-Object -Append $log
$result = diskpart /s $tmpScript 2>&1
$result | Tee-Object -Append $log

"VHDX after: $([math]::Round((Get-Item $vhdx).Length/1GB,1)) GB" | Tee-Object -Append $log
"Free C: $([math]::Round((Get-PSDrive C).Free/1GB,1)) GB" | Tee-Object -Append $log
"[$(Get-Date)] DONE" | Tee-Object -Append $log
