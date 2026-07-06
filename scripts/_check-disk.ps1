$v = "C:\Users\gheno\AppData\Local\wsl\{0fa6a1b8-39ef-4ca2-ae78-f6eabf8bb04d}\ext4.vhdx"
if (Test-Path $v) {
    $gb = [math]::Round((Get-Item $v).Length / 1GB, 2)
    Write-Host "VHDX main: $gb GB"
}
$c = Get-PSDrive C
Write-Host "C: libre: $([math]::Round($c.Free/1GB, 2)) GB | utilise: $([math]::Round($c.Used/1GB, 2)) GB"
