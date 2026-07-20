$ErrorActionPreference = "Continue"
$log = "C:\Users\gheno\citevision\scripts\compact-log.txt"
"" | Set-Content $log

function Log($msg) {
    Write-Host $msg
    Add-Content $log $msg
}

function Compact-Vhdx($vhdx) {
    $before = (Get-Item -LiteralPath $vhdx).Length
    Log "`n=== Compact $vhdx ($([math]::Round($before/1GB,2)) GB) ==="

    $dpScript = "C:\Users\gheno\citevision\scripts\diskpart-tmp.txt"
    @(
        "select vdisk file=`"$vhdx`"",
        "attach vdisk readonly",
        "compact vdisk",
        "detach vdisk",
        "exit"
    ) | Set-Content $dpScript -Encoding ASCII

    $dpOut = "C:\Users\gheno\citevision\scripts\diskpart-out.txt"
    $dpErr = "C:\Users\gheno\citevision\scripts\diskpart-err.txt"
    $p = Start-Process -FilePath "diskpart.exe" -ArgumentList "/s `"$dpScript`"" -Wait -PassThru -RedirectStandardOutput $dpOut -RedirectStandardError $dpErr -NoNewWindow
    if (Test-Path $dpOut) { Log (Get-Content $dpOut -Raw) }
    if (Test-Path $dpErr) {
        $err = Get-Content $dpErr -Raw
        if ($err) { Log "STDERR: $err" }
    }
    Log "diskpart exit: $($p.ExitCode)"

    $after = (Get-Item -LiteralPath $vhdx).Length
    $freed = [math]::Round(($before - $after) / 1GB, 2)
    Log "Result: $([math]::Round($before/1GB,2)) GB -> $([math]::Round($after/1GB,2)) GB (freed $freed GB)"
}

$cBefore = (Get-PSDrive C).Free
Log "C: libre avant: $([math]::Round($cBefore/1GB, 2)) GB"

# fstrim already done after purge; skip to avoid encoding/shell issues. Optional refresh:
Log "=== fstrim inside WSL (mark free blocks) ==="
$trim = wsl -d Ubuntu-24.04 -- bash -lc 'sudo fstrim -av; sync; df -h /' 2>&1
Log ($trim | Out-String)

Log "=== WSL shutdown ==="
wsl --shutdown | Out-Null
Start-Sleep -Seconds 20

Log "=== set-sparse false (required for diskpart compact) ==="
$sparseOff = wsl --manage Ubuntu-24.04 --set-sparse false 2>&1
Log ($sparseOff | Out-String)
Start-Sleep -Seconds 3

$wslRoot = "C:\Users\gheno\AppData\Local\wsl"
$vhdxList = @()
if (Test-Path $wslRoot) {
    $vhdxList += Get-ChildItem -LiteralPath $wslRoot -Recurse -Filter "ext4.vhdx" -Force -ErrorAction SilentlyContinue
}
$dockerVhdx = "C:\Users\gheno\AppData\Local\Docker\wsl\main\ext4.vhdx"
if (Test-Path $dockerVhdx) {
    $vhdxList += Get-Item -LiteralPath $dockerVhdx
}

$vhdxList = $vhdxList | Sort-Object Length -Descending | Select-Object -Unique FullName, Length, Attributes

foreach ($item in $vhdxList) {
    Compact-Vhdx $item.FullName
}

Log "=== set-sparse true (auto reclaim later) ==="
$sparseOn = wsl --manage Ubuntu-24.04 --set-sparse true 2>&1
Log ($sparseOn | Out-String)

$cAfter = (Get-PSDrive C).Free
Log "`nC: libre apres: $([math]::Round($cAfter/1GB, 2)) GB (gain $([math]::Round(($cAfter-$cBefore)/1GB,2)) GB)"
Log "`nDone."
