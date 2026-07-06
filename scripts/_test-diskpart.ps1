$vhdx = "C:\Users\gheno\AppData\Local\wsl\{0fa6a1b8-39ef-4ca2-ae78-f6eabf8bb04d}\ext4.vhdx"
$script = @"
select vdisk file="$vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
$sf = "$env:TEMP\compact-vhdx.txt"
Set-Content $sf $script -Encoding ASCII
Write-Host "Running diskpart..."
$result = & diskpart /s $sf 2>&1
Write-Host $result
Remove-Item $sf -Force -ErrorAction SilentlyContinue
