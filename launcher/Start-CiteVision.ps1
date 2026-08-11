#Requires -Version 5.1
<#
.SYNOPSIS
  Start the CiteVision product stack.
.NOTES
  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1
  Exit 0 when services, health gate, and Gemini probe pass.
  ASCII-only body for Windows PowerShell 5.1 encoding safety (like Stop-CiteVision.ps1).
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')

function ConvertTo-WslPath {
  param([Parameter(Mandatory = $true)][string]$WinPath)
  $full = [System.IO.Path]::GetFullPath($WinPath)
  if ($full -match '^([A-Za-z]):\\?(.*)$') {
    $drive = $Matches[1].ToLowerInvariant()
    $rest = ($Matches[2] -replace '\\', '/')
    return ("/mnt/{0}/{1}" -f $drive, $rest).TrimEnd('/')
  }
  return ($full -replace '\\', '/')
}

function ConvertTo-AsciiSafe {
  param([AllowNull()][string]$Text)
  if ($null -eq $Text) { return "" }
  $s = $Text
  # Common UTF-8 mojibake / accents -> ASCII
  $s = $s -replace [char]0x00E9, 'e'  # e acute
  $s = $s -replace [char]0x00E8, 'e'
  $s = $s -replace [char]0x00EA, 'e'
  $s = $s -replace [char]0x00E0, 'a'
  $s = $s -replace [char]0x00E2, 'a'
  $s = $s -replace [char]0x00F4, 'o'
  $s = $s -replace [char]0x00FB, 'u'
  $s = $s -replace [char]0x00F9, 'u'
  $s = $s -replace [char]0x00E7, 'c'
  $s = $s -replace [char]0x00EE, 'i'
  $s = $s -replace [char]0x00EF, 'i'
  $s = $s -replace [char]0x00C9, 'E'
  $s = $s -replace [char]0x2014, '-'  # em dash
  $s = $s -replace [char]0x2013, '-'  # en dash
  $s = $s -replace [char]0x2026, '...' # ellipsis
  $s = $s -replace [char]0x00AB, '"'
  $s = $s -replace [char]0x00BB, '"'
  $s = $s -replace [char]0x201C, '"'
  $s = $s -replace [char]0x201D, '"'
  $s = $s -replace [char]0x2018, "'"
  $s = $s -replace [char]0x2019, "'"
  # Known mojibake sequences when UTF-8 was read as CP1252
  $s = $s -replace 'Cit├®Vision', 'CiteVision'
  $s = $s -replace '├®', 'e'
  $s = $s -replace '├¿', 'e'
  $s = $s -replace '├¿', 'e'
  $s = $s -replace '├á', 'a'
  $s = $s -replace '├┤', 'o'
  $s = $s -replace '├»', 'u'
  $s = $s -replace '├º', 'c'
  $s = $s -replace 'ÔÇö', '-'
  $s = $s -replace 'ÔÇô', '-'
  $s = $s -replace 'ÔÇª', '...'
  $s = $s -replace 'ÔÇª', '...'
  # Strip remaining non-ASCII
  $sb = New-Object System.Text.StringBuilder
  foreach ($ch in $s.ToCharArray()) {
    $code = [int]$ch
    if ($code -ge 32 -and $code -le 126) {
      [void]$sb.Append($ch)
    } elseif ($code -eq 9) {
      [void]$sb.Append(' ')
    } else {
      [void]$sb.Append('?')
    }
  }
  return $sb.ToString()
}

function Test-CiteStartNoise {
  param([string]$Line)
  if ($Line -match 'live-preview|Sync critical paths|mirror ->|/mnt/c/Users/|skip missing|ALL_SYNC_OK|WSL_OK') {
    return $true
  }
  if ($Line -match '^\s*waiting\.\.\.') { return $true }
  if ($Line -match 'Expecting value:') { return $true }
  if ($Line -match '^\s*Container\s+citevision') { return $true }
  if ($Line -match '^\s*citevision-v2-[a-z0-9_-]+\s*$') { return $true }
  if ($Line -match 'gemini_key=present') { return $true }
  if ($Line -match '^\s*\{?\s*"(active_rules|service|status|heal_failed|healed)"') { return $true }
  if ($Line -match '^\s*[\{\[]' -and $Line -match '[\]\}]\s*$') { return $true }
  if ($Line -match '^\s*"(active_rules|dedup_ttl|last_match|mqtt_|matches_total|service|status)"') { return $true }
  if ($Line -match 'models_all_ok=|yolo_loaded:|face_loaded:|plate_loaded:|yolo_cuda:') { return $true }
  if ($Line -match 'PREFLIGHT_VALIDATE|Stop pidfile:') { return $true }
  if ($Line -match 'AI health: ok|Backend health: ok|Backend started \(pid=') { return $true }
  if ($Line -match '^\s*\d+\[OK\]') { return $true }
  return $false
}

function Write-CiteStartLine {
  param([AllowNull()][string]$Line)
  if ($null -eq $Line) { return }
  $t = ("{0}" -f $Line).TrimEnd()
  if ($t.Length -eq 0) { return }
  if (Test-CiteStartNoise $t) { return }

  $d = ConvertTo-AsciiSafe $t
  $d = $d -replace '/home/[^/\s]+/citevision[^/\s]*', 'runtime'
  $d = $d -replace 'ROOT=/[^\s]+', 'ROOT=runtime'
  $d = $d -replace 'CITEVISION_ROOT=/[^\s]+', 'CITEVISION_ROOT=runtime'
  $d = $d.Trim()
  if ($d.Length -eq 0) { return }

  if ($d -match '^===\s*(.+?)\s*===') {
    Write-Host ("  > {0}" -f (ConvertTo-AsciiSafe $Matches[1].Trim())) -ForegroundColor Cyan
    return
  }
  if ($d -match '^\[OK\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor Green
    return
  }
  if ($d -match '^\[FAIL\]' -or $d -match '^\[ERR\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor Red
    return
  }
  if ($d -match '^\[WARN\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor Yellow
    return
  }
  if ($d -match '^\[INFO\]' -or $d -match '^\[\.\.\.\]' -or $d -match '^\[\u2026\]' -or $d -match '^\[\?\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor DarkGray
    return
  }
  if ($d -match '^\[GATE OK\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor Green
    return
  }
  if ($d -match '^\[GATE FAIL\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor Red
    return
  }
  # Keep short useful lines only
  if ($d.Length -gt 220) { return }
  Write-Host ("  {0}" -f $d) -ForegroundColor Gray
}

try {
  $WslRoot = Resolve-CiteVisionWslRoot
} catch {
  Write-Host ("[FAIL] {0}" -f (ConvertTo-AsciiSafe $_.Exception.Message)) -ForegroundColor Red
  exit 1
}

$ProductRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$WslProductRoot = ConvertTo-WslPath $ProductRoot

Write-Host ""
Write-Host "CiteVision START" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/4] Runtime check" -ForegroundColor Cyan
$prev = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
wsl -d $Distro -e true 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  $ErrorActionPreference = $prev
  Write-Host "[FAIL] Runtime environment is not available." -ForegroundColor Red
  exit 1
}
$ErrorActionPreference = $prev

$probe = ('test -f "{0}/scripts/lib/start-full-stack.sh"' -f $WslRoot)
wsl -d $Distro -- bash -lc $probe
if ($LASTEXITCODE -ne 0) {
  Write-Host "[FAIL] CiteVision runtime is incomplete. Reinstall or repair the product." -ForegroundColor Red
  exit 1
}
Write-Host "[OK] Runtime ready" -ForegroundColor Green

Write-Host "[2/4] Refresh product files" -ForegroundColor Cyan
$syncPreview = ('SRC="{0}"; DST="{1}"; SCRIPT="$SRC/scripts/lib/sync-live-preview-ui.sh"; if [ -f "$SCRIPT" ]; then bash "$SCRIPT" "$SRC" "$DST" >/dev/null 2>&1 || true; fi' -f $WslProductRoot, $WslRoot)
wsl -d $Distro -- bash -lc $syncPreview | Out-Null
Write-Host "[OK] Refresh done" -ForegroundColor Green

Write-Host "[3/4] Starting stack (Docker, AI, backend, Frigate...)" -ForegroundColor Cyan
Write-Host "      Progress lines appear below; first boot can take several minutes." -ForegroundColor DarkGray
Write-Host ""

# Stop-like: UTF-8 no BOM wrapper script, then stream filtered output.
$bash = @'
#!/usr/bin/env bash
set -uo pipefail
ROOT="${CV_ROOT:-$HOME/citevision-v2}"
case "$ROOT" in
  /mnt/*)
    echo "[FAIL] Refuse ROOT under /mnt/* (got $ROOT)"
    exit 1
    ;;
esac
cd "$ROOT" || { echo "[FAIL] cannot cd ROOT"; exit 1; }
export STRICT_INSTALL_HEALTH=1
export PYTHONUNBUFFERED=1
export CITEVISION_ASCII_LOG=1
if command -v stdbuf >/dev/null 2>&1; then
  exec stdbuf -oL -eL bash scripts/lib/start-full-stack.sh
fi
exec bash scripts/lib/start-full-stack.sh
'@

$tmp = Join-Path $env:TEMP "citevision-start-all.sh"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($tmp, ($bash -replace "`r`n", "`n" -replace "`r", "`n"), $utf8NoBom)

$remoteCmd = ('cat > /tmp/citevision-start-all.sh; sed -i "s/\r$//" /tmp/citevision-start-all.sh; CV_ROOT={0} bash /tmp/citevision-start-all.sh' -f $WslRoot)

$logLines = New-Object System.Collections.Generic.List[string]
Get-Content -LiteralPath $tmp -Raw | & wsl.exe -d $Distro -- bash -lc $remoteCmd 2>&1 | ForEach-Object {
  $line = "$_"
  [void]$logLines.Add($line)
  Write-CiteStartLine $line
}
$rc = $LASTEXITCODE
$joined = [string]::Join("`n", $logLines)

Write-Host ""
Write-Host "[4/4] Start result" -ForegroundColor Cyan

if ($rc -ne 0) {
  Write-Host "[FAIL] CiteVision could not start completely." -ForegroundColor Red
  if ($joined -match 'GEMINI_PROBE_FAILED|gemini_probe FAILED|gemini_configured missing|GEMINI_PROBE') {
    Write-Host ""
    Write-Host "[FAIL] Vision AI key missing or unreachable." -ForegroundColor Red
    Write-Host "Set your API key, then start again:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Set-CiteVisionGeminiKey.ps1 -ApiKey 'YOUR_API_KEY'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1" -ForegroundColor Cyan
    Write-Host ""
  }
  exit $rc
}

Write-Host "[OK] CiteVision is ready" -ForegroundColor Green
Write-Host "     Open http://127.0.0.1:5174" -ForegroundColor Green
Write-Host ""
exit 0
