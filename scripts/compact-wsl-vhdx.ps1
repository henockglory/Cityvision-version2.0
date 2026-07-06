$ErrorActionPreference = "Continue"
$log = "C:\Users\gheno\citevision\scripts\compact-log.txt"
"" | Set-Content $log

function Log($msg) {
    Write-Host $msg
    Add-Content $log $msg
}

Log "=== WSL shutdown ==="
wsl --shutdown | Out-Null
Start-Sleep -Seconds 4

# Enable sparse VHD (WSL 2.0+ on Win 11) then compact
foreach ($distro in @("Ubuntu-24.04", "Ubuntu")) {
    Log "=== wsl --manage $distro --set-sparse true ==="
    $r = wsl --manage $distro --set-sparse true 2>&1
    Log $r
}

$vhdxMain = "C:\Users\gheno\AppData\Local\wsl\{0fa6a1b8-39ef-4ca2-ae78-f6eabf8bb04d}\ext4.vhdx"
$vhdxList = @(
    $vhdxMain,
    "C:\Users\gheno\AppData\Local\wsl\{38284c04-1ae8-4eaa-8237-45737e4497e2}\ext4.vhdx",
    "C:\Users\gheno\AppData\Local\Docker\wsl\main\ext4.vhdx"
)

$cBefore = (Get-PSDrive C).Free
Log "C: libre avant: $([math]::Round($cBefore/1GB, 2)) GB"

foreach ($vhdx in $vhdxList) {
    if (-not (Test-Path $vhdx)) { continue }
    $before = (Get-Item $vhdx).Length
    Log "`n=== Compact $vhdx ($([math]::Round($before/1GB,2)) GB) ==="

    # Method 1: diskpart
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

    $after = (Get-Item $vhdx).Length
    $freed = [math]::Round(($before - $after) / 1GB, 2)
    Log "Result: $([math]::Round($before/1GB,2)) GB -> $([math]::Round($after/1GB,2)) GB (freed $freed GB)"
}

$cAfter = (Get-PSDrive C).Free
Log "`nC: libre apres: $([math]::Round($cAfter/1GB, 2)) GB (gain $([math]::Round(($cAfter-$cBefore)/1GB,2)) GB)"

Log "`nDone."
