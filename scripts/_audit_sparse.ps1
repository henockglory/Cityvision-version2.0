# Check if VHDX is sparse
$path = "C:\Users\gheno\AppData\Local\wsl\{c5515942-ee60-4c07-8acf-bef2540fe7e1}\ext4.vhdx"
Write-Host "=== fsutil sparse query ==="
fsutil sparse queryflag $path
Write-Host "=== file size vs allocation ==="
$f = Get-Item $path
Write-Host ("LengthBytes={0} ({1:N2} GB)" -f $f.Length, ($f.Length/1GB))
# NTFS allocated size via Get-Item is Length; use fsutil
fsutil file queryvaliddata $path 2>&1 | Select-Object -First 5
Write-Host "=== wsl --manage help sparse ==="
wsl --help 2>&1 | Select-String -Pattern 'sparse' -Context 0,2
