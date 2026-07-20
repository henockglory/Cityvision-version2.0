# Compact WSL ext4.vhdx after demo retention purge (run as Administrator).
# Scheduled: every 30 minutes via install-demo-retention-schedule.ps1
$ErrorActionPreference = "Continue"
$Root = "C:\Users\gheno\citevision"
$Log = Join-Path $Root "scripts\demo-retention-compact.log"
$RetainMin = if ($env:FRIGATE_DEMO_RETENTION_MIN) { $env:FRIGATE_DEMO_RETENTION_MIN } else { "30" }

function Log($msg) {
    $line = "[$(Get-Date -Format o)] $msg"
    Write-Host $line
    Add-Content -Path $Log -Value $line
}

Log "=== demo retention compact (retain ${RetainMin}m) ==="
$cBefore = (Get-PSDrive C).Free
Log "C: free before: $([math]::Round($cBefore/1GB, 2)) GB"

# Purge inside WSL first (no shutdown yet)
$purge = wsl -d Ubuntu-24.04 bash -lc "FRIGATE_DEMO_RETENTION_MIN=$RetainMin ~/citevision-v2/scripts/demo-retention-purge.sh" 2>&1
Log $purge

Log "WSL shutdown for VHDX compact..."
wsl --shutdown | Out-Null
Start-Sleep -Seconds 12

wsl --manage Ubuntu-24.04 --set-sparse false 2>&1 | Out-Null

$vhdx = "C:\Users\gheno\AppData\Local\wsl\{c5515942-ee60-4c07-8acf-bef2540fe7e1}\ext4.vhdx"
if (-not (Test-Path -LiteralPath $vhdx)) {
    $found = Get-ChildItem "C:\Users\gheno\AppData\Local\wsl" -Recurse -Filter "ext4.vhdx" -Force -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $vhdx = $found.FullName }
}

if (Test-Path -LiteralPath $vhdx) {
    $before = (Get-Item -LiteralPath $vhdx).Length
    Log "VHDX before: $([math]::Round($before/1GB, 2)) GB"

    $dpScript = Join-Path $Root "scripts\diskpart-purge-compact.txt"
    @(
        "select vdisk file=`"$vhdx`"",
        "attach vdisk readonly",
        "compact vdisk",
        "detach vdisk",
        "exit"
    ) | Set-Content $dpScript -Encoding ASCII

    $dpOut = Join-Path $Root "scripts\diskpart-out.txt"
    $p = Start-Process -FilePath "diskpart.exe" -ArgumentList "/s `"$dpScript`"" -Wait -PassThru -RedirectStandardOutput $dpOut -RedirectStandardError (Join-Path $Root "scripts\diskpart-err.txt") -NoNewWindow
    if (Test-Path $dpOut) { Log (Get-Content $dpOut -Raw) }
    Log "diskpart exit: $($p.ExitCode)"

    $after = (Get-Item -LiteralPath $vhdx).Length
    Log "VHDX after: $([math]::Round($after/1GB, 2)) GB (freed $([math]::Round(($before-$after)/1GB, 2)) GB)"
} else {
    Log "WARN: ext4.vhdx not found"
}

wsl --manage Ubuntu-24.04 --set-sparse true --allow-unsafe 2>&1 | Out-Null

$cAfter = (Get-PSDrive C).Free
Log "C: free after: $([math]::Round($cAfter/1GB, 2)) GB (gain $([math]::Round(($cAfter-$cBefore)/1GB, 2)) GB)"
Log "=== done ==="
