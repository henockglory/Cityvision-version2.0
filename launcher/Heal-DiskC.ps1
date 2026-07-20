#Requires -Version 5.1
<#
.SYNOPSIS
  Heal disque C: — purge Frigate/MinIO (WSL) + Temp Windows + compact VHDX (élévation manuelle OK).
.NOTES
  powershell -ExecutionPolicy Bypass -File ops\Heal-DiskC.ps1
  Si diskpart demande l'admin : valider l'UAC. Relancer en "Exécuter en tant qu'administrateur" si besoin.
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
$Log = Join-Path $env:TEMP "citevision-heal-disk-last.log"

function Log([string]$m) {
  $line = "[{0}] {1}" -f (Get-Date -Format o), $m
  Write-Host $line
  Add-Content -Path $Log -Value $line
}

"" | Set-Content $Log
$cBefore = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
Log "C: free BEFORE = $cBefore GB"

# --- 1) Purge Frigate / MinIO / fstrim in WSL (preserves newest PASS artefacts) ---
$purgeBash = @'
#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT" || exit 1
echo "=== ensure docker ==="
bash scripts/_start_dockerd_wsl.sh 2>/dev/null || true
for i in $(seq 1 40); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker start citevision-v2-postgres citevision-v2-minio 2>/dev/null || true
sleep 2
echo "=== stop media consumers ==="
pkill -f 'uvicorn citevision_ai.main|citevision-api|rules-engine' 2>/dev/null || true
docker stop citevision-v2-frigate 2>/dev/null || true
sleep 1
echo "=== truncate alerts/events ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "TRUNCATE TABLE alerts RESTART IDENTITY CASCADE;" 2>/dev/null || true
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "TRUNCATE TABLE events RESTART IDENTITY CASCADE;" 2>/dev/null || true
echo "=== purge minio evidence ==="
docker exec citevision-v2-minio sh -c 'rm -rf /data/citevision-evidence && mkdir -p /data/citevision-evidence' 2>/dev/null || true
echo "=== purge frigate volumes ==="
for vol in infra_frigate_recordings infra_frigate_clips infra_frigate_cache infra_frigate_exports; do
  docker run --rm -v "${vol}:/v" alpine sh -c "find /v -mindepth 1 -delete; du -sh /v" 2>/dev/null || true
done
echo "=== disable demo rules ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%';" 2>/dev/null || true
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
    if not d.is_dir(): continue
    subs=sorted([p for p in d.iterdir() if p.is_dir()], key=lambda p:p.name, reverse=True)
    for p in subs[:2]: keep.add(p.resolve())
for p in root.rglob("*"):
    if p.is_dir() and p.parent.name in ("speeding","red_light","phone","seatbelt","counting") and p.resolve() not in keep:
        if p.parent == root: continue
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
[System.IO.File]::WriteAllText($tmpPurge, ($purgeBash -replace "`r`n","`n" -replace "`r","`n"))
Log "=== WSL Frigate/MinIO purge + fstrim ==="
Get-Content -LiteralPath $tmpPurge -Raw | wsl -d $Distro -- bash -c "cat > /tmp/citevision-heal-purge.sh && sed -i 's/\r`$//' /tmp/citevision-heal-purge.sh && bash /tmp/citevision-heal-purge.sh"
Log "WSL purge exit=$LASTEXITCODE"

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
Log "Temp entries removed (best-effort)=$removed"

# Safe junk under Windows citevision edit tree
@(
  "C:\Users\gheno\citevision\frontend\test-results",
  "C:\Users\gheno\citevision\frontend\dist"
) | ForEach-Object {
  if (Test-Path $_) {
    Remove-Item $_ -Recurse -Force -ErrorAction SilentlyContinue
    Log "removed $_"
  }
}

# --- 3) Compact VHDX (may need elevation — user validates UAC) ---
Log "=== Compact WSL VHDX ==="
Log "Shutting down WSL…"
wsl --shutdown
Start-Sleep -Seconds 20

$vhdxList = @()
$wslRoot = Join-Path $env:LOCALAPPDATA "wsl"
if (Test-Path $wslRoot) {
  $vhdxList += Get-ChildItem -LiteralPath $wslRoot -Recurse -Filter "ext4.vhdx" -Force -ErrorAction SilentlyContinue
}
$dockerVhdx = Join-Path $env:LOCALAPPDATA "Docker\wsl\main\ext4.vhdx"
if (Test-Path $dockerVhdx) { $vhdxList += Get-Item -LiteralPath $dockerVhdx }

function Invoke-Compact([string]$vhdx) {
  $before = (Get-Item -LiteralPath $vhdx).Length
  Log "Compact $vhdx ($([math]::Round($before/1GB,2)) GB)"
  $dp = Join-Path $env:TEMP "citevision-diskpart.txt"
  @(
    "select vdisk file=`"$vhdx`"",
    "attach vdisk readonly",
    "compact vdisk",
    "detach vdisk",
    "exit"
  ) | Set-Content -Path $dp -Encoding ASCII

  # Prefer elevated diskpart; fall back to current token (user may already be admin)
  $out = Join-Path $env:TEMP "citevision-diskpart-out.txt"
  try {
    $p = Start-Process -FilePath "diskpart.exe" -ArgumentList "/s `"$dp`"" -Verb RunAs -Wait -PassThru -WindowStyle Hidden
    Log "diskpart elevated exit=$($p.ExitCode)"
  } catch {
    Log "Elevation refused or failed ($($_.Exception.Message)) — trying non-elevated"
    try {
      $p2 = Start-Process -FilePath "diskpart.exe" -ArgumentList "/s `"$dp`"" -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $out -RedirectStandardError (Join-Path $env:TEMP "citevision-diskpart-err.txt")
      Log "diskpart exit=$($p2.ExitCode)"
      if (Test-Path $out) { Log (Get-Content $out -Raw) }
    } catch {
      Log "diskpart FAILED: $($_.Exception.Message)"
      Log "Action: re-run this script via 'Run as administrator'."
    }
  }
  $after = (Get-Item -LiteralPath $vhdx).Length
  Log "VHDX $($([math]::Round($before/1GB,2))) -> $($([math]::Round($after/1GB,2))) GB (delta $([math]::Round(($before-$after)/1GB,2)) GB)"
}

foreach ($item in ($vhdxList | Sort-Object Length -Descending)) {
  Invoke-Compact $item.FullName
}

# Wake WSL
Log "Wake WSL…"
wsl -d $Distro -- echo WSL_OK | Out-Null

$cAfter = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
Log "C: free AFTER = $cAfter GB (gain $([math]::Round($cAfter - $cBefore, 2)) GB)"
Log "DONE — log: $Log"
Write-Host ""
Write-Host "Heal terminé. C: $cBefore GB -> $cAfter GB libres."
Write-Host "Relance stack: launcher\Start-CiteVision.ps1"
exit 0
