#Requires -Version 5.1
<#
.SYNOPSIS
  Heal disk C: - purge Frigate/MinIO (WSL) + Temp Windows + compact VHDX (manual elevation OK).
.NOTES
  powershell -ExecutionPolicy Bypass -File launcher\Heal-DiskC.ps1
  If diskpart asks for admin: accept UAC. Re-run as Administrator if needed.
  ASCII-only for Windows PowerShell 5.1 encoding safety.
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')
try {
  $WslRoot = Resolve-CiteVisionWslRoot
} catch {
  Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
  exit 1
}
$Log = Join-Path $env:TEMP "citevision-heal-disk-last.log"

function Log([string]$m) {
  $line = "[{0}] {1}" -f (Get-Date -Format o), $m
  Write-Host $line
  Add-Content -Path $Log -Value $line
}

"" | Set-Content $Log
$cBefore = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
Log ("C: free BEFORE = {0} GB" -f $cBefore)

$prev = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
wsl -d $Distro -e true 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  $ErrorActionPreference = $prev
  Write-Host ("[FAIL] WSL distro '{0}' not available" -f $Distro) -ForegroundColor Red
  exit 1
}
$ErrorActionPreference = $prev

# --- 1) Purge Frigate / MinIO / fstrim in WSL (preserves newest PASS artefacts) ---
$purgeBash = @'
#!/usr/bin/env bash
set -uo pipefail
ROOT="${CV_ROOT:-$HOME/citevision-v2}"
case "$ROOT" in
  /mnt/*)
    echo "[FAIL] Refuse ROOT under /mnt/* (got $ROOT)"
    exit 1
    ;;
esac
cd "$ROOT" || exit 1
echo "=== ensure docker ==="
bash scripts/_start_dockerd_wsl.sh 2>/dev/null || true
for i in $(seq 1 40); do
  if docker info >/dev/null 2>&1; then break; fi
  sleep 2
done
docker start citevision-v2-postgres citevision-v2-minio 2>/dev/null || true
sleep 2
echo "=== stop media consumers (preserve .env + Gemini keyfiles) ==="
pkill -f 'uvicorn citevision_ai.main|citevision-api|rules-engine|frigate_watchdog|watch-infra-ports|watch-business-readiness|watch-ai-ingest|watch-rules-engine|watch-backend' 2>/dev/null || true
docker stop citevision-v2-frigate citevision-v2-go2rtc 2>/dev/null || true
docker rm -f citevision-v2-go2rtc 2>/dev/null || true
sleep 1
echo "=== truncate alerts/events ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "TRUNCATE TABLE alerts RESTART IDENTITY CASCADE;" 2>/dev/null || true
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "TRUNCATE TABLE events RESTART IDENTITY CASCADE;" 2>/dev/null || true
echo "=== purge minio evidence ==="
docker exec citevision-v2-minio sh -c 'rm -rf /data/citevision-evidence; mkdir -p /data/citevision-evidence' 2>/dev/null || true
echo "=== purge frigate volumes ==="
for vol in infra_frigate_recordings infra_frigate_clips infra_frigate_cache infra_frigate_exports; do
  docker run --rm -v "${vol}:/v" alpine sh -c "find /v -mindepth 1 -delete; du -sh /v" 2>/dev/null || true
done
echo "=== disable demo rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Demo%';" 2>/dev/null || true
echo "=== prune images (not containers) ==="
docker image prune -af 2>/dev/null || true
echo "=== keep newest 2 artefacts / alias ==="
python3 - <<'PY'
from pathlib import Path
import shutil
root = Path.home() / "citevision-v2" / "validation-evidence"
keep=set()
for alias in ("speeding","red_light","phone","seatbelt","counting"):
    d=root/alias
    if not d.is_dir():
        continue
    subs=sorted([p for p in d.iterdir() if p.is_dir()], key=lambda p:p.name, reverse=True)
    for p in subs[:2]:
        keep.add(p.resolve())
for p in root.rglob("*"):
    if p.is_dir() and p.parent.name in ("speeding","red_light","phone","seatbelt","counting") and p.resolve() not in keep:
        if p.parent == root:
            continue
        if len(p.relative_to(root).parts)==2:
            shutil.rmtree(p, ignore_errors=True)
            print("rm", p)
print("kept", len(keep))
PY
echo "=== fstrim ==="
sudo fstrim -av 2>/dev/null || sudo fstrim -v / || true
sync
df -h / /mnt/c | head -5
echo PURGE_WSL_OK
'@

$tmpPurge = Join-Path $env:TEMP "citevision-heal-purge.sh"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($tmpPurge, ($purgeBash -replace "`r`n", "`n" -replace "`r", "`n"), $utf8NoBom)
Log "=== WSL Frigate/MinIO purge + fstrim ==="
# PS 5.1-safe: no && in PowerShell double-quoted args.
$remotePurge = ('cat > /tmp/citevision-heal-purge.sh; sed -i "s/\r$//" /tmp/citevision-heal-purge.sh; CV_ROOT={0} bash /tmp/citevision-heal-purge.sh' -f $WslRoot)
Get-Content -LiteralPath $tmpPurge -Raw | wsl -d $Distro -- bash -lc $remotePurge
Log ("WSL purge exit={0}" -f $LASTEXITCODE)

# --- 2) Windows user Temp ---
Log "=== Windows Temp sweep ==="
$tempRoot = Join-Path $env:LOCALAPPDATA "Temp"
$removed = 0
Get-ChildItem -LiteralPath $tempRoot -Force -ErrorAction SilentlyContinue | ForEach-Object {
  try {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
    $removed++
  } catch { }
}
Log ("Temp entries removed (best-effort)={0}" -f $removed)

@(
  "C:\Users\gheno\citevision\frontend\test-results",
  "C:\Users\gheno\citevision\frontend\dist"
) | ForEach-Object {
  if (Test-Path $_) {
    Remove-Item $_ -Recurse -Force -ErrorAction SilentlyContinue
    Log ("removed {0}" -f $_)
  }
}

# --- 3) Compact VHDX (may need elevation - user validates UAC) ---
Log "=== Compact WSL VHDX ==="
Log "Shutting down WSL..."
wsl --shutdown
Start-Sleep -Seconds 20

$vhdxList = @()
$wslLocal = Join-Path $env:LOCALAPPDATA "wsl"
if (Test-Path $wslLocal) {
  $vhdxList += Get-ChildItem -LiteralPath $wslLocal -Recurse -Filter "ext4.vhdx" -Force -ErrorAction SilentlyContinue
}
$dockerVhdx = Join-Path $env:LOCALAPPDATA "Docker\wsl\main\ext4.vhdx"
if (Test-Path $dockerVhdx) { $vhdxList += Get-Item -LiteralPath $dockerVhdx }

function Invoke-Compact([string]$vhdx) {
  $beforeBytes = (Get-Item -LiteralPath $vhdx).Length
  $beforeGb = [math]::Round($beforeBytes / 1GB, 2)
  Log ("Compact {0} ({1} GB)" -f $vhdx, $beforeGb)
  $dp = Join-Path $env:TEMP "citevision-diskpart.txt"
  $lines = @(
    ('select vdisk file="{0}"' -f $vhdx),
    'attach vdisk readonly',
    'compact vdisk',
    'detach vdisk',
    'exit'
  )
  $lines | Set-Content -Path $dp -Encoding ASCII

  $out = Join-Path $env:TEMP "citevision-diskpart-out.txt"
  $err = Join-Path $env:TEMP "citevision-diskpart-err.txt"
  try {
    $p = Start-Process -FilePath "diskpart.exe" -ArgumentList @('/s', $dp) -Verb RunAs -Wait -PassThru -WindowStyle Hidden
    Log ("diskpart elevated exit={0}" -f $p.ExitCode)
  } catch {
    Log ("Elevation refused or failed ({0}) - trying non-elevated" -f $_.Exception.Message)
    try {
      $p2 = Start-Process -FilePath "diskpart.exe" -ArgumentList @('/s', $dp) -Wait -PassThru -NoNewWindow -RedirectStandardOutput $out -RedirectStandardError $err
      Log ("diskpart exit={0}" -f $p2.ExitCode)
      if (Test-Path $out) { Log (Get-Content $out -Raw) }
    } catch {
      Log ("diskpart FAILED: {0}" -f $_.Exception.Message)
      Log "Action: re-run this script via Run as administrator."
    }
  }
  $afterBytes = (Get-Item -LiteralPath $vhdx).Length
  $afterGb = [math]::Round($afterBytes / 1GB, 2)
  $deltaGb = [math]::Round(($beforeBytes - $afterBytes) / 1GB, 2)
  Log ("VHDX {0} -> {1} GB (delta {2} GB)" -f $beforeGb, $afterGb, $deltaGb)
}

foreach ($item in ($vhdxList | Sort-Object Length -Descending)) {
  Invoke-Compact $item.FullName
}

Log "Wake WSL..."
wsl -d $Distro -- echo WSL_OK | Out-Null

$cAfter = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
$gain = [math]::Round($cAfter - $cBefore, 2)
Log ("C: free AFTER = {0} GB (gain {1} GB)" -f $cAfter, $gain)
Log ("DONE - log: {0}" -f $Log)
Write-Host ""
Write-Host ("Heal done. C: {0} GB -> {1} GB free." -f $cBefore, $cAfter)
Write-Host "Restart stack: launcher\Start-CiteVision.ps1"
exit 0
