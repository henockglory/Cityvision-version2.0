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

# Step 1: mark deleted blocks inside WSL before shutdown (required for VHD shrink).
Log "=== fstrim + zero-fill inside WSL ==="
$trim = wsl -d Ubuntu-24.04 bash -lc "sudo fstrim -av && (dd if=/dev/zero of=/tmp/zero.fill bs=1M 2>/dev/null || true) && rm -f /tmp/zero.fill && sync && df -h /" 2>&1
Log $trim

Log "=== WSL shutdown ==="
wsl --shutdown | Out-Null
Start-Sleep -Seconds 8

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
    $path = $item.FullName
    if ($item.Attributes -band [IO.FileAttributes]::SparseFile) {
        Log "`n=== SKIP (SparseFile) $path ($([math]::Round($item.Length/1GB,2)) GB) ==="
        continue
    }
    Compact-Vhdx $path
}

$cAfter = (Get-PSDrive C).Free
Log "`nC: libre apres: $([math]::Round($cAfter/1GB, 2)) GB (gain $([math]::Round(($cAfter-$cBefore)/1GB,2)) GB)"
Log "`nDone."
