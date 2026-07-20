$paths = @(
    'C:\Users\gheno\AppData\Local\wsl\{38284c04-1ae8-4eaa-8237-45737e4497e2}\ext4.vhdx',
    'C:\Users\gheno\AppData\Local\wsl\{c5515942-ee60-4c07-8acf-bef2540fe7e1}\ext4.vhdx',
    'C:\Users\gheno\AppData\Local\Docker\wsl\main\ext4.vhdx'
)
foreach ($p in $paths) {
    if (Test-Path -LiteralPath $p) {
        $i = Get-Item -LiteralPath $p
        $gb = [math]::Round($i.Length / 1GB, 2)
        $sparse = ($i.Attributes -band [IO.FileAttributes]::SparseFile) -ne 0
        Write-Host "$gb GB  sparse=$sparse  $p"
    }
}
$c = Get-PSDrive C
$d = Get-PSDrive D
Write-Host "C: libre $([math]::Round($c.Free/1GB,2)) GB"
Write-Host "D: libre $([math]::Round($d.Free/1GB,2)) GB"
