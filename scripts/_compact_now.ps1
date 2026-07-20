$ErrorActionPreference = "Continue"
$log = "C:\Users\gheno\citevision\scripts\compact-log.txt"
"" | Set-Content $log

function Log($msg) {
    Write-Host $msg
    Add-Content $log $msg
}

function Compact-Vhdx($vhdx) {
    $before = (Get-Item -LiteralPath $vhdx).Length
    Log ""
    Log "=== Compact $vhdx ($([math]::Round($before/1GB,2)) GB) ==="

    $dpScript = "C:\Users\gheno\citevision\scripts\diskpart-tmp.txt"
    @(
        "select vdisk file=`"$vhdx`"",
        "attach vdisk readonly",
        "compact vdisk",
        "detach vdisk",
        "exit"
    ) | Set-Content $dpScript -Encoding ASCII

    $dpOut = "C:\Users\gheno\citevision\scripts\diskpart-out.txt"
    $p = Start-Process -FilePath "diskpart.exe" -ArgumentList "/s `"$dpScript`"" -Wait -PassThru -RedirectStandardOutput $dpOut -RedirectStandardError "C:\Users\gheno\citevision\scripts\diskpart-err.txt" -NoNewWindow
    if (Test-Path $dpOut) { Log (Get-Content $dpOut -Raw) }
    if (Test-Path "C:\Users\gheno\citevision\scripts\diskpart-err.txt") {
        $err = Get-Content "C:\Users\gheno\citevision\scripts\diskpart-err.txt" -Raw
        if ($err) { Log "STDERR: $err" }
    }
    Log "diskpart exit: $($p.ExitCode)"

    $after = (Get-Item -LiteralPath $vhdx).Length
    $freed = [math]::Round(($before - $after) / 1GB, 2)
    Log "Result: $([math]::Round($before/1GB,2)) GB -> $([math]::Round($after/1GB,2)) GB (freed $freed GB)"
}

$cBefore = (Get-PSDrive C).Free
Log "C: libre avant: $([math]::Round($cBefore/1GB, 2)) GB"

Log "=== WSL shutdown ==="
wsl --shutdown | Out-Null
Start-Sleep -Seconds 20

Log "=== set-sparse false ==="
Log (wsl --manage Ubuntu-24.04 --set-sparse false 2>&1)
Start-Sleep -Seconds 3

$vhdxList = @()
$wslRoot = "C:\Users\gheno\AppData\Local\wsl"
if (Test-Path $wslRoot) {
    $vhdxList += Get-ChildItem -LiteralPath $wslRoot -Recurse -Filter "ext4.vhdx" -Force -ErrorAction SilentlyContinue
}
$dockerVhdx = "C:\Users\gheno\AppData\Local\Docker\wsl\main\ext4.vhdx"
if (Test-Path $dockerVhdx) {
    $vhdxList += Get-Item -LiteralPath $dockerVhdx
}

foreach ($item in ($vhdxList | Sort-Object Length -Descending)) {
    Compact-Vhdx $item.FullName
}

Log "=== set-sparse true ==="
Log (wsl --manage Ubuntu-24.04 --set-sparse true 2>&1)

$cAfter = (Get-PSDrive C).Free
Log ""
Log "C: libre apres: $([math]::Round($cAfter/1GB, 2)) GB (gain $([math]::Round(($cAfter-$cBefore)/1GB,2)) GB)"
Log "Done."
