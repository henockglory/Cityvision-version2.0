$v = Get-ChildItem -LiteralPath 'C:\Users\gheno\AppData\Local\wsl' -Recurse -Filter 'ext4.vhdx' -Force -ErrorAction SilentlyContinue |
    Sort-Object Length -Descending | Select-Object -First 1
if ($v) {
    $gb = [math]::Round($v.Length / 1GB, 2)
    Write-Host "VHDX WSL: $gb GB ($($v.FullName))"
}
$c = Get-PSDrive C
Write-Host "C: libre: $([math]::Round($c.Free/1GB, 2)) GB | utilise: $([math]::Round($c.Used/1GB, 2)) GB"
