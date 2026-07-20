# Register Windows scheduled task: demo retention compact every 30 minutes (Administrator).
$TaskName = "CiteVision-DemoRetentionCompact"
$Root = "C:\Users\gheno\citevision"
$Script = Join-Path $Root "scripts\demo-retention-compact.ps1"
$Cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Script`""

schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
schtasks /Create /TN $TaskName /TR $Cmd /SC MINUTE /MO 30 /RU SYSTEM /RL HIGHEST /F
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Scheduled task $TaskName every 30 minutes (SYSTEM)"
} else {
    Write-Host "[FAIL] schtasks exit $LASTEXITCODE - run this script as Administrator"
    exit 1
}
